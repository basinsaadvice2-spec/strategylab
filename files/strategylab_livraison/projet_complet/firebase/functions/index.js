/**
 * StrategyLab — mise à jour automatique des données de marché.
 *
 * Une seule Cloud Function planifiée (Cloud Scheduler la déclenche toute
 * seule, toutes les heures, sans que personne ne clique) :
 *   - PÉTROLE (WTI) : source officielle EIA via FRED, gratuite, sans clé.
 *       La source ne publie qu'UNE valeur de clôture par jour : revérifier
 *       toutes les heures sert à récupérer la nouvelle valeur dès qu'elle
 *       sort, pas à créer des données plus fréquentes.
 *   - OR (XAU/USD) : Twelve Data (offre gratuite, nécessite une clé API à
 *       mettre dans functions/.env). Sans clé, l'or est simplement ignoré
 *       (aucune donnée inventée, jamais).
 *
 * Stockage Firestore :
 *   markets/{SYMBOL}                 -> méta (lastDate, source, updatedAt...)
 *   markets/{SYMBOL}/years/{YYYY}    -> { year, bars: [{d,o,h,l,c,v}, ...] }
 * (un document par année pour rester loin de la limite de 1 Mo par doc, et
 * parce que Firestore interdit les tableaux imbriqués -> barres en objets.)
 */
const { onSchedule } = require("firebase-functions/v2/scheduler");
const { defineString } = require("firebase-functions/params");
const logger = require("firebase-functions/logger");
const admin = require("firebase-admin");

admin.initializeApp();
const db = admin.firestore();
const { FieldValue } = admin.firestore;

const TWELVEDATA_API_KEY = defineString("TWELVEDATA_API_KEY", { default: "" });
const YEARS_BACK = 11; // ~10 ans d'historique + l'année en cours

const round = (x) => Math.round(x * 10000) / 10000;

// ---------- Sources ----------

async function fetchOil() {
  const res = await fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILWTICO", {
    signal: AbortSignal.timeout(30000),
  });
  if (!res.ok) throw new Error(`FRED HTTP ${res.status}`);
  const text = await res.text();

  const rows = [];
  for (const line of text.split(/\r?\n/).slice(1)) {
    const [date, raw] = line.split(",");
    const close = parseFloat(raw);
    // FRED met "." quand il n'y a pas de cotation (jour férié) : on saute. Les prix <= 0
    // (ex. WTI en avril 2020) sont aussi écartés : le moteur de backtest suppose des prix > 0.
    if (!date || raw === "." || !Number.isFinite(close) || close <= 0) continue;
    rows.push({ date, close });
  }
  if (rows.length === 0) throw new Error("FRED: aucune donnée exploitable");

  // La source ne donne qu'une clôture par jour (pas de haut/bas/volume).
  // Barres reconstruites : open = clôture précédente, high/low = bornes
  // open/close, volume = 0. Marqué ohlcApprox dans la méta pour que l'app
  // l'affiche clairement.
  let prev = null;
  const bars = rows.map(({ date, close }) => {
    const open = prev === null ? close : prev;
    prev = close;
    return { d: date, o: round(open), h: round(Math.max(open, close)),
             l: round(Math.min(open, close)), c: round(close), v: 0 };
  });
  return { bars, label: "Pétrole WTI", source: "EIA via FRED (DCOILWTICO)",
           ohlcApprox: true, hasVolume: false };
}

async function fetchGold(apiKey) {
  const url = "https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1day" +
              `&outputsize=3000&order=ASC&apikey=${encodeURIComponent(apiKey)}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(30000) });
  const json = await res.json();
  if (!res.ok || json.status === "error" || !Array.isArray(json.values)) {
    throw new Error(`Twelve Data: ${json.message || "HTTP " + res.status}`);
  }
  const bars = json.values
    .map((x) => ({ d: String(x.datetime).slice(0, 10), o: round(+x.open), h: round(+x.high),
                   l: round(+x.low), c: round(+x.close), v: Number(x.volume) || 0 }))
    .filter((b) => [b.o, b.h, b.l, b.c].every((n) => Number.isFinite(n) && n > 0)
                   && b.h >= Math.max(b.o, b.c) - 1e-9 && b.l <= Math.min(b.o, b.c) + 1e-9);
  if (bars.length === 0) throw new Error("Twelve Data: aucune barre exploitable");
  return { bars, label: "Or (XAU/USD)", source: "Twelve Data",
           ohlcApprox: false, hasVolume: bars.some((b) => b.v > 0) };
}

// ---------- Écriture Firestore ----------

async function upsertAsset(symbol, { bars, label, source, ohlcApprox, hasVolume }) {
  const metaRef = db.collection("markets").doc(symbol);
  const meta = (await metaRef.get()).data() || {};
  const last = bars[bars.length - 1];

  // Garde-fou d'intégrité : une série d'historique ne doit pas rétrécir. Si la source
  // renvoie nettement moins de barres qu'avant (réponse tronquée, erreur, source
  // corrompue), on refuse d'écrire plutôt que d'abîmer des données saines.
  if (meta.sourceBarCount && bars.length < meta.sourceBarCount * 0.9) {
    throw new Error(`${symbol}: source suspecte (${bars.length} barres reçues contre ` +
                    `${meta.sourceBarCount} connues) — écriture annulée.`);
  }

  if (meta.backfilled && meta.lastDate && meta.lastDate >= last.d) {
    await metaRef.set({ checkedAt: FieldValue.serverTimestamp() }, { merge: true });
    logger.info(`${symbol}: déjà à jour (${meta.lastDate}).`);
    return;
  }

  const minYear = new Date().getUTCFullYear() - YEARS_BACK;
  const fromYear = meta.backfilled && meta.lastDate
    ? Math.max(minYear, Number(meta.lastDate.slice(0, 4)))
    : minYear;

  const byYear = {};
  for (const b of bars) {
    const y = Number(b.d.slice(0, 4));
    if (y < fromYear) continue;
    (byYear[y] = byYear[y] || []).push(b);
  }

  const batch = db.batch();
  for (const [year, yb] of Object.entries(byYear)) {
    batch.set(metaRef.collection("years").doc(year), { year: Number(year), bars: yb });
  }
  batch.set(metaRef, {
    symbol, label, source, ohlcApprox, hasVolume,
    lastDate: last.d, backfilled: true, sourceBarCount: bars.length,
    updatedAt: FieldValue.serverTimestamp(), checkedAt: FieldValue.serverTimestamp(),
  }, { merge: true });
  await batch.commit();
  logger.info(`${symbol}: ${Object.keys(byYear).length} année(s) écrite(s), dernière date ${last.d}.`);
}

// ---------- Fonction planifiée ----------

exports.updateMarketData = onSchedule(
  { schedule: "every 1 hours", timeoutSeconds: 120, memory: "256MiB" },
  async () => {
    // Chaque actif est traité séparément : si l'un échoue, l'autre continue.
    try {
      await upsertAsset("OIL", await fetchOil());
    } catch (e) {
      logger.error("OIL: échec de la mise à jour", e);
    }

    const goldKey = TWELVEDATA_API_KEY.value();
    if (!goldKey) {
      logger.warn("GOLD: aucune clé TWELVEDATA_API_KEY dans functions/.env — or ignoré.");
    } else {
      try {
        await upsertAsset("GOLD", await fetchGold(goldKey));
      } catch (e) {
        logger.error("GOLD: échec de la mise à jour", e);
      }
    }
  }
);
