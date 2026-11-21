// Test de bout en bout SANS navigateur : exécute le vrai script de la page contre un vrai serveur Python,
// avec un faux DOM et une bibliothèque de graphiques simulée. Ne remplace pas un essai dans un vrai navigateur.
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const mode = process.argv[3];
const scripts = [...html.matchAll(/<script(?: [^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim());
class El {
  constructor(tag) { this.tagName = tag; this.children = []; this._text = ""; this.className = ""; this.hidden = false; this.disabled = false; this.value = "";
    this.style = {}; this.attrs = {}; this.clientWidth = 600; this.clientHeight = 300; this.parentNode = null; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get firstChild() { return this.children[0]; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter(x => x !== c); }
  setAttribute(k, v) { this.attrs[k] = String(v); } getAttribute(k) { return this.attrs[k]; }
  click() { if (this.onclick) return this.onclick(); } scrollIntoView() {}
}
const reg = {};
global.document = { getElementById: id => reg[id] || (reg[id] = new El("#" + id)), createElement: t => new El(t),
  createElementNS: (ns, t) => new El(t), createTextNode: t => { const e = new El("#text"); e._text = String(t); return e; }, body: new El("body") };
for (const m of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*\bhidden\b[^>]*>/g)) document.getElementById(m[1]).hidden = true;   // attribut hidden du HTML
const store = {}; global.localStorage = { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = v; } };
const calls = { charts: 0, removed: 0, area: 0 };
function series() { return { setData() {}, setMarkers() {}, createPriceLine() {} }; }
function chart() { calls.charts++; return { addCandlestickSeries: series, addHistogramSeries: series, addLineSeries: series, addAreaSeries() { calls.area++; return series(); },
  priceScale: () => ({ applyOptions() {} }), applyOptions() {}, remove() { calls.removed++; },
  timeScale: () => ({ subscribeVisibleLogicalRangeChange() {}, setVisibleLogicalRange() {}, fitContent() {} }), subscribeCrosshairMove() {} }; }
global.window = { LightweightCharts: { createChart: chart, CrosshairMode: { Normal: 0 }, LineStyle: { Dashed: 2 } }, addEventListener() {} };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(cond, label, ms = 8000) { const t0 = Date.now(); while (!cond()) { if (Date.now() - t0 > ms) throw new Error("timeout: " + label); await sleep(25); } }
const ok = (c, msg) => { console.log((c ? "OK   " : "ÉCHEC") + " " + msg); if (!c) process.exitCode = 1; };
const $ = id => document.getElementById(id);
const conds = () => $("builder").children.filter(c => c.className === "cond").length;
const idle = () => $("run").disabled === false && $("run").textContent === "Lancer le test";

(async () => {
  for (const s of scripts) (0, eval)(s);
  if (mode === "offline") {            // adresse intégrée mais serveur injoignable : jamais de saisie d'adresse
    await waitFor(() => $("alert").hidden === false, "message d'erreur");
    ok(/injoignable/.test($("alert").textContent), "serveur injoignable -> message clair : " + $("alert").textContent);
    ok(!/adresse/i.test($("alert").textContent) && $("apiBox").hidden === true, "aucune demande d'adresse à l'utilisateur final");
    return;
  }
  if (mode === "generic") {            // page générique (administrateur) : saisie d'adresse proposée
    await waitFor(() => $("apiBox").hidden === false, "boîte administrateur");
    ok(true, "page générique : saisie de l'adresse proposée à l'administrateur");
    $("apiInput").value = "http://pas-https.example"; $("apiSave").onclick();
    ok(/https/.test($("alert").textContent), "adresse sans https refusée");
    return;
  }
  await waitFor(() => $("kpis").children.length === 5 && idle(), "ouverture + premier test automatique");
  ok(calls.charts >= 3 && calls.area === 1, "le graphique s'affiche dès l'ouverture (prix, RSI, capital) : " + calls.charts + " graphiques");
  const [oil, gold] = $("watchlist").children;
  ok(oil.getAttribute("aria-pressed") === "true" && !oil.disabled && /\d/.test(oil.textContent), "liste de suivi : pétrole sélectionné, avec prix : " + oil.textContent);
  ok(gold.disabled === true && /TWELVEDATA/.test(gold.title), "or désactivé avec la raison (clé manquante)");
  ok($("periods").children.length === 8 && $("periods").children[5].getAttribute("aria-pressed") === "true", "8 périodes (3J … 10A, Perso.), 5A sélectionnée");
  ok(/Pétrole/.test($("sym").textContent) && /Données jusqu/.test($("dataChip").textContent), "en-tête : " + $("sym").textContent + " | " + $("dataChip").textContent);
  ok(conds() === 2, "règle d'achat : 2 conditions par défaut");

  let before = calls.removed; $("periods").children[3].onclick();            // 1A : nouveau test automatique
  await waitFor(() => calls.removed > before && idle(), "test auto après changement de période");
  ok(true, "changer de période relance le test automatiquement");

  $("ttPerf").onclick(); ok($("paneOverview").hidden && !$("panePerf").hidden && $("perfBody").children.length > 12, "résumé de la performance : " + $("perfBody").children.length + " lignes");
  $("ttProps").onclick(); ok(/RSI \(14\) < 30/.test($("propsBody").textContent) && /SMA 200/.test($("propsBody").textContent), "propriétés : règles affichées en clair");
  $("ttTrades").onclick(); ok(!$("paneTrades").hidden && $("tbody").children.length >= 1, "liste des trades : " + $("tbody").children.length + " ligne(s)");
  $("ttOverview").onclick(); ok(!$("paneOverview").hidden, "retour à l'aperçu");

  $("tabSell").onclick(); ok($("tabSell").getAttribute("aria-pressed") === "true", "onglet vente");
  $("builder").children.find(c => c.className === "add").onclick(); ok(conds() === 3, "ajout d'une condition de vente");
  $("builder").children.filter(c => c.className === "cond")[2].children[1].children[2].onclick(); ok(conds() === 2, "suppression d'une condition");

  before = calls.removed; $("run2").onclick(); await waitFor(() => calls.removed > before && idle(), "test manuel");
  ok(true, "« Lancer le test » (panneau de droite) relance le calcul, anciens graphiques supprimés");

  $("fRisk").value = "abc"; $("run").onclick(); await sleep(50); ok(/invalide/.test($("alert").textContent), "champ non numérique refusé côté page");
  $("fRisk").value = "500"; $("run").onclick(); await waitFor(() => /compris entre/.test($("alert").textContent), "refus serveur");
  ok(true, "valeur hors limites refusée par le serveur : " + $("alert").textContent); $("fRisk").value = "2";

  $("periods").children[7].onclick(); ok($("custom").hidden === false, "période personnalisée : champs de dates affichés");
  before = calls.removed; $("cStart").value = "2023-01-02"; $("cEnd").value = "2024-06-28"; $("cStart").onchange();
  await waitFor(() => calls.removed > before && idle(), "test période personnalisée"); ok(/Période personnalisée/.test($("propsBody").textContent), "période personnalisée exécutée et affichée dans les propriétés");

  $("ttProj").onclick(); $("projBtn").onclick(); await waitFor(() => $("pbody").children.length === 4, "projection");
  ok(true, "projection : 4 échéances");
  $("collapse").onclick(); ok(/collapsed/.test($("tester").className), "panneau du bas réductible");
  global.URL.createObjectURL = () => "blob:x"; let threw = false; try { $("export").onclick(); } catch (e) { threw = true; console.log(e.message); } ok(!threw, "export CSV sans erreur");
})().catch(e => { console.log("ÉCHEC", e.message); process.exitCode = 1; });
