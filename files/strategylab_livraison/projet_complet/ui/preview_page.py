"""
Page d'aperçu INTERACTIVE autonome (un seul fichier HTML), générée par Python.

Tous les résultats (rendement, trades, drawdown, projection...) sont calculés ici par
le moteur Python pour chaque combinaison actif × période × stratégie ; la page ne fait
que choisir quel résultat précalculé afficher, avec les graphiques TradingView. Elle
sert à valider le rendu SANS installer Streamlit. Les données de démonstration sont
SIMULÉES : l'application réelle utilise les données réelles (data/live_providers.py).

Régénérer : python -m ui.preview_page [fichier_sortie.html]
"""
import json
import sys

import numpy as np
import pandas as pd

from ui import app_logic as L
from ui import tv_chart

PERIODS = ["1Y", "3Y", "5Y", "10Y"]
PERIOD_LABELS = {"1Y": "1 an", "3Y": "3 ans", "5Y": "5 ans", "10Y": "10 ans"}

C = L.make_condition
STRATEGIES = {
    "rsi_sma200": {
        "name": "RSI 30/70 + SMA 200 (exemple du cahier des charges)",
        "desc": "Achat : RSI < 30 ET prix > SMA 200. Vente : RSI > 70 ET prix < SMA 200. Très sélective : peu de trades.",
        "buy": L.make_rule("AND", [C("RSI (14)", "<", "Valeur", 30), C("Prix", ">", "Indicateur", right_label="SMA 200")]),
        "sell": L.make_rule("AND", [C("RSI (14)", ">", "Valeur", 70), C("Prix", "<", "Indicateur", right_label="SMA 200")]),
    },
    "rsi_40_62": {
        "name": "RSI 40/62",
        "desc": "Achat : RSI < 40. Vente : RSI > 62. Plus de trades, donc une statistique plus lisible.",
        "buy": L.make_rule("AND", [C("RSI (14)", "<", "Valeur", 40)]),
        "sell": L.make_rule("OR", [C("RSI (14)", ">", "Valeur", 62)]),
    },
    "ema_cross": {
        "name": "Croisement EMA 12 / EMA 26 + ADX",
        "desc": "Achat : EMA 12 > EMA 26 ET ADX > 20. Vente : EMA 12 < EMA 26. Suivi de tendance.",
        "buy": L.make_rule("AND", [C("EMA 12", ">", "Indicateur", right_label="EMA 26"), C("ADX (14)", ">", "Valeur", 20)]),
        "sell": L.make_rule("OR", [C("EMA 12", "<", "Indicateur", right_label="EMA 26")]),
    },
    "boll_mfi": {
        "name": "Bollinger + MFI (utilise le volume)",
        "desc": "Achat : prix < bande de Bollinger basse ET MFI < 30. Vente : prix > bande haute OU MFI > 70. Nécessite un volume réel.",
        "buy": L.make_rule("AND", [C("Prix", "<", "Indicateur", right_label="Bollinger basse"), C("MFI (14)", "<", "Valeur", 30)]),
        "sell": L.make_rule("OR", [C("Prix", ">", "Indicateur", right_label="Bollinger haute"), C("MFI (14)", ">", "Valeur", 70)]),
    },
}

BACKTEST = dict(cash=10000, risk_pct=0.02, stop_loss_pct=0.03, take_profit_pct=0.06,
                commission_rate=0.001, slippage_rate=0.0005)


def demo_dataset(start_price: float, vol: float, seed: int, with_volume: bool, n: int = 2700) -> pd.DataFrame:
    """Série SIMULÉE (marche aléatoire) pour la démonstration uniquement."""
    rng = np.random.default_rng(seed)
    ts = pd.bdate_range(end="2026-10-30", periods=n, tz="UTC")
    close = start_price * np.exp(np.cumsum(rng.normal(0.0001, vol, n)))
    op = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, vol * 0.35, n)) * close
    return pd.DataFrame({
        "timestamp": ts, "open": op, "high": np.maximum(op, close) + spread,
        "low": np.minimum(op, close) - spread, "close": close,
        "volume": rng.integers(50_000, 300_000, n).astype(float) if with_volume else 0.0,
    })


def _compact_trades(trades: pd.DataFrame, limit: int = 60) -> list:
    rows = []
    for t in trades.tail(limit).itertuples():
        rows.append([pd.Timestamp(t.entry_time).strftime("%Y-%m-%d"), pd.Timestamp(t.exit_time).strftime("%Y-%m-%d"),
                     round(float(t.entry_price), 2), round(float(t.exit_price), 2),
                     round(float(t.pnl_dollars), 2), str(t.exit_reason)])
    return rows


def compute_all(datasets: dict) -> dict:
    """datasets: {clé: {"label": str, "df": DataFrame}} -> structure JSON-able."""
    assets = {}
    for key, ds in datasets.items():
        periods = {}
        for pk in PERIODS:
            strategies, base = {}, None
            for sk, strat in STRATEGIES.items():
                res = L.run_analysis(ds["df"], pk, strat["buy"], strat["sell"], BACKTEST["cash"],
                                     BACKTEST["risk_pct"], BACKTEST["stop_loss_pct"], BACKTEST["take_profit_pct"],
                                     BACKTEST["commission_rate"], BACKTEST["slippage_rate"], ds["label"])
                p, r = res["chart_payload"], res["report"]
                if base is None:   # bougies, volume, SMA, RSI : identiques pour toutes les stratégies
                    base = {k: p[k] for k in ("candles", "volume", "overlays", "rsi")}
                strategies[sk] = {
                    "markers": p["markers"], "trades": _compact_trades(res["trades"]),
                    "report": {k: r[k] for k in ("return_pct", "final_equity", "n_trades", "win_rate_pct",
                                                 "max_drawdown_pct", "profit_factor", "reliable_sample")},
                }
            periods[pk] = {"base": base, "strategies": strategies}
        view = L.projection_view(ds["df"], ds["label"])
        assets[key] = {"label": ds["label"], "periods": periods,
                       "projection": {"payload": view["payload"], "table": view["table"]}}
    return {"assets": assets, "periods": [{"key": k, "label": PERIOD_LABELS[k]} for k in PERIODS],
            "strategies": {k: {"name": v["name"], "desc": v["desc"]} for k, v in STRATEGIES.items()},
            "theme": tv_chart.THEME}


def _json_default(o):
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"Non sérialisable : {type(o)}")


def build_preview_html(datasets: dict) -> str:
    data = json.dumps(compute_all(datasets), ensure_ascii=False, default=_json_default).replace("<", "\\u003c")
    return (_PAGE.replace("__LWC_URL__", tv_chart.LWC_URL).replace("__RENDER_JS__", tv_chart.RENDER_JS)
            .replace("__DATA__", data).replace("__BG__", tv_chart.THEME["bg"]))


_PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>StrategyLab — aperçu</title>
<style>
  :root { --bg:__BG__; --panel:#111a2e; --line:#1d2a47; --txt:#e6edf7; --dim:#9fb0cc; --up:#22c55e; --down:#ef4444; --blue:#2563eb; --amber:#f59e0b; }
  * { box-sizing:border-box; }
  html, body { margin:0; background:var(--bg); color:var(--txt); font-family:-apple-system,'Segoe UI',Roboto,sans-serif; }
  #app { max-width:980px; margin:0 auto; padding:max(14px, env(safe-area-inset-top)) 14px 28px; }
  .badge { display:inline-block; font-size:12px; color:var(--amber); border:1px solid var(--amber); border-radius:99px; padding:4px 10px; margin-bottom:10px; }
  h1 { font-size:20px; margin:0 0 4px; } .sub { color:var(--dim); font-size:13px; margin:0 0 14px; line-height:1.45; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px; margin-bottom:12px; }
  .lbl { font-size:12px; color:var(--dim); margin:0 0 6px; }
  .seg { display:flex; gap:6px; flex-wrap:wrap; }
  .seg button { flex:1; min-width:56px; background:#0e1730; border:1px solid var(--line); color:var(--dim); padding:9px 6px; border-radius:9px; font-size:13px; }
  .seg button.on { background:var(--blue); border-color:var(--blue); color:#fff; font-weight:600; }
  select { width:100%; background:#0e1730; color:var(--txt); border:1px solid var(--line); border-radius:9px; padding:10px; font-size:14px; }
  .desc { font-size:12px; color:var(--dim); margin:8px 0 0; line-height:1.45; }
  .metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:12px; }
  .m { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:9px 10px; }
  .m .k { font-size:11px; color:var(--dim); } .m .v { font-size:16px; font-weight:700; margin-top:2px; }
  .up { color:var(--up); } .down { color:var(--down); }
  .warn { font-size:12px; color:var(--amber); background:rgba(245,158,11,.08); border-radius:9px; padding:8px 10px; margin-bottom:12px; }
  .chartbox { background:var(--bg); border:1px solid var(--line); border-radius:14px; overflow:hidden; margin-bottom:12px; }
  .wrap { position:relative; } .legend { position:absolute; top:8px; left:10px; z-index:5; font-size:12px; color:var(--dim); pointer-events:none; line-height:1.5; }
  .legend b { color:var(--txt); font-size:13px; }
  .chart { height:340px; } .rsi { height:120px; margin-top:2px; } .rsilabel { font-size:11px; color:var(--dim); padding:4px 10px 0; }
  .tabs { display:flex; gap:6px; margin-bottom:10px; } .tabs button { flex:1; background:#0e1730; border:1px solid var(--line); color:var(--dim); padding:10px; border-radius:9px; font-size:13px; }
  .tabs button.on { background:var(--panel); color:var(--txt); border-color:var(--blue); font-weight:600; }
  .tab { display:none; } .tab.on { display:block; }
  .scroll { overflow-x:auto; } table { width:100%; border-collapse:collapse; font-size:12px; }
  th { text-align:left; color:var(--dim); font-weight:500; padding:6px 5px; border-bottom:1px solid var(--line); white-space:nowrap; }
  td { padding:6px 5px; border-bottom:1px solid var(--line); white-space:nowrap; font-variant-numeric:tabular-nums; }
  .note { font-size:11.5px; color:var(--dim); line-height:1.5; margin:8px 0 0; }
  .attr { font-size:11px; color:var(--dim); text-align:center; margin-top:10px; } .attr a { color:#7aa2ff; text-decoration:none; }
</style></head><body><div id="app">
  <span class="badge">DÉMO — données simulées</span>
  <h1>StrategyLab — aperçu de la simulation</h1>
  <p class="sub">Tous les chiffres sont calculés par le moteur Python du projet ; cette page choisit seulement quel résultat afficher. Les données sont tirées au hasard : aucune valeur indicative. L'application réelle utilise les vraies données.</p>

  <div class="card"><p class="lbl">1 · Actif</p><div class="seg" id="assets"></div>
    <p class="lbl" style="margin-top:12px">2 · Période</p><div class="seg" id="periods"></div>
    <p class="lbl" style="margin-top:12px">3 · Stratégie</p><select id="strat"></select><p class="desc" id="desc"></p></div>

  <div class="metrics" id="metrics"></div>
  <div class="warn" id="warn" style="display:none"></div>

  <div class="chartbox"><div class="wrap"><div class="legend" id="legend"></div><div class="chart" id="main"></div></div>
    <div class="rsilabel" id="rsilabel">RSI (14) — surachat au-dessus de 70, survente en dessous de 30</div><div class="rsi" id="rsi"></div></div>

  <div class="tabs"><button id="tt" class="on">Trades</button><button id="tp">Projection statistique</button></div>
  <div class="tab on" id="tab-trades"><div class="card scroll"><table><thead><tr><th>Entrée</th><th>Sortie</th><th>Prix entrée</th><th>Prix sortie</th><th>Résultat $</th><th>Raison</th></tr></thead><tbody id="tbody"></tbody></table></div></div>
  <div class="tab" id="tab-proj"><div class="card">
    <p class="note" style="margin:0 0 8px">Plage de probabilité issue de la volatilité historique — <b>pas une prédiction</b>. Hypothèses : même dispersion que par le passé, aucune tendance supposée. Bougies pleines = historique, bougies ambrées = plage simulée (une par mois).</p>
    <div class="chartbox" style="margin-bottom:8px"><div class="wrap"><div class="legend" id="plegend"></div><div class="chart" id="pmain"></div></div></div>
    <div class="scroll"><table><thead><tr><th>Échéance</th><th>Date</th><th>10e pct.</th><th>Médiane</th><th>90e pct.</th></tr></thead><tbody id="pbody"></tbody></table></div></div></div>
  <div class="attr">Graphiques : <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a> · Copyright © TradingView, Inc.</div>
</div>
<script src="__LWC_URL__"></script>
<script>__RENDER_JS__</script>
<script>
(function () {
  const D = __DATA__, T = D.theme, $ = function (id) { return document.getElementById(id); };
  const st = { asset: Object.keys(D.assets)[0], period: '3Y', strat: Object.keys(D.strategies)[0], tab: 'trades' };
  let hMain = null, hProj = null;

  function seg(el, items, current, onPick) {
    el.textContent = '';
    items.forEach(function (it) {
      const b = document.createElement('button'); b.textContent = it.label; if (it.key === current) b.className = 'on';
      b.onclick = function () { onPick(it.key); }; el.appendChild(b);
    });
  }
  function cell(tr, text, cls) { const td = document.createElement('td'); td.textContent = text; if (cls) td.className = cls; tr.appendChild(td); }
  function pct(v) { return (v >= 0 ? '+' : '') + v.toFixed(2) + ' %'; }

  function renderControls() {
    seg($('assets'), Object.keys(D.assets).map(function (k) { return { key: k, label: D.assets[k].label }; }), st.asset, function (k) { st.asset = k; renderAll(); });
    seg($('periods'), D.periods, st.period, function (k) { st.period = k; renderAll(); });
    const sel = $('strat'); sel.textContent = '';
    Object.keys(D.strategies).forEach(function (k) { const o = document.createElement('option'); o.value = k; o.textContent = D.strategies[k].name; if (k === st.strat) o.selected = true; sel.appendChild(o); });
    sel.onchange = function () { st.strat = sel.value; renderAll(); };
    $('desc').textContent = D.strategies[st.strat].desc;
  }
  function renderMetrics(r) {
    const pf = r.profit_factor === null ? '—' : (r.profit_factor === Infinity ? '∞' : r.profit_factor.toFixed(2));
    const items = [['Rendement', pct(r.return_pct), r.return_pct >= 0 ? 'up' : 'down'], ['Capital final', Math.round(r.final_equity).toLocaleString('fr-FR') + ' $', ''],
      ['Trades', String(r.n_trades), ''], ['Win rate', r.n_trades ? r.win_rate_pct.toFixed(1) + ' %' : '—', ''],
      ['Drawdown max', r.max_drawdown_pct.toFixed(2) + ' %', 'down'], ['Profit factor', pf, '']];
    const box = $('metrics'); box.textContent = '';
    items.forEach(function (it) {
      const d = document.createElement('div'); d.className = 'm';
      const k = document.createElement('div'); k.className = 'k'; k.textContent = it[0];
      const v = document.createElement('div'); v.className = 'v ' + it[2]; v.textContent = it[1];
      d.appendChild(k); d.appendChild(v); box.appendChild(d);
    });
    const w = $('warn');
    if (!r.reliable_sample) { w.style.display = 'block'; w.textContent = 'Échantillon faible (' + r.n_trades + ' trade' + (r.n_trades > 1 ? 's' : '') + ') : à interpréter avec prudence.'; }
    else w.style.display = 'none';
  }
  function renderTrades(rows) {
    const tb = $('tbody'); tb.textContent = '';
    if (!rows.length) { const tr = document.createElement('tr'); cell(tr, 'Aucun trade sur cette configuration.'); tb.appendChild(tr); return; }
    rows.slice().reverse().forEach(function (r) {
      const tr = document.createElement('tr');
      cell(tr, r[0]); cell(tr, r[1]); cell(tr, r[2].toFixed(2)); cell(tr, r[3].toFixed(2));
      cell(tr, (r[4] >= 0 ? '+' : '') + r[4].toFixed(2), r[4] >= 0 ? 'up' : 'down'); cell(tr, r[5]); tb.appendChild(tr);
    });
  }
  function renderMain() {
    const A = D.assets[st.asset], pd = A.periods[st.period], s = pd.strategies[st.strat];
    const label = D.periods.filter(function (p) { return p.key === st.period; })[0].label;
    const payload = Object.assign({}, pd.base, { markers: s.markers, title: A.label + ' · ' + label });
    if (hMain) hMain.destroy();
    hMain = window.renderTV(payload, T, { main: $('main'), rsi: $('rsi'), rsilabel: $('rsilabel'), legend: $('legend') });
    renderMetrics(s.report); renderTrades(s.trades);
  }
  function renderProjection() {
    if (st.tab !== 'proj') return;
    const pr = D.assets[st.asset].projection;
    if (hProj) hProj.destroy();
    hProj = window.renderTV(Object.assign({}, pr.payload, { rsi: [] }), T, { main: $('pmain'), rsi: null, rsilabel: null, legend: $('plegend') });
    const tb = $('pbody'); tb.textContent = '';
    pr.table.forEach(function (r) {
      const tr = document.createElement('tr'); cell(tr, r.echeance); cell(tr, r.date); cell(tr, r.p10.toFixed(2)); cell(tr, r.mediane.toFixed(2)); cell(tr, r.p90.toFixed(2)); tb.appendChild(tr);
    });
  }
  function renderAll() { renderControls(); renderMain(); renderProjection(); }
  function setTab(t) {
    st.tab = t; $('tt').className = t === 'trades' ? 'on' : ''; $('tp').className = t === 'proj' ? 'on' : '';
    $('tab-trades').className = 'tab' + (t === 'trades' ? ' on' : ''); $('tab-proj').className = 'tab' + (t === 'proj' ? ' on' : '');
    renderProjection();
  }
  $('tt').onclick = function () { setTab('trades'); }; $('tp').onclick = function () { setTab('proj'); };
  window.addEventListener('resize', function () { if (hMain) hMain.resize(); if (hProj) hProj.resize(); });
  renderAll();
})();
</script></body></html>
"""

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "strategylab_preview.html"
    demo = {
        "OIL": {"label": "Pétrole (démo)", "df": demo_dataset(65, 0.017, 21, with_volume=False)},
        "GOLD": {"label": "Or (démo)", "df": demo_dataset(1900, 0.009, 8, with_volume=True)},
    }
    html = build_preview_html(demo)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"{out} écrit ({len(html) / 1e6:.2f} Mo)")
