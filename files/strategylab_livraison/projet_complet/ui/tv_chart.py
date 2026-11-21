"""
Graphique "à la TradingView" : bibliothèque open source Lightweight Charts™ de
TradingView (Apache-2.0), version 4.2.0 figée. Elle ne fait que DESSINER : toutes
les données et tous les calculs viennent de Python.

Licence : l'attribution à TradingView (lien vers tradingview.com) est obligatoire ;
elle est affichée sous le graphique. Pour la conformité stricte, reprends le texte
exact du fichier NOTICE du dépôt github.com/tradingview/lightweight-charts.

Séries journalières uniquement (temps = "AAAA-MM-JJ").
"""
import json
import math

import pandas as pd

LWC_URL = "https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"

THEME = {
    "bg": "#131722", "grid": "#1e222d", "text": "#d1d4dc", "up": "#089981", "down": "#f23645",
    "sma_fast": "#ff9800", "sma_slow": "#2962ff", "rsi": "#7e57c2", "proj": "#ff9800",
}


def _day(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _num(x, nd=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def df_to_candles(df: pd.DataFrame) -> list:
    return [{"time": _day(r.timestamp), "open": _num(r.open), "high": _num(r.high),
             "low": _num(r.low), "close": _num(r.close)} for r in df.itertuples()]


def df_to_volume(df: pd.DataFrame) -> list:
    """Vide si l'actif n'a pas de volume réel (ex. pétrole)."""
    if "volume" not in df.columns or not (df["volume"] > 0).any():
        return []
    up, down = THEME["up"] + "66", THEME["down"] + "66"
    return [{"time": _day(r.timestamp), "value": _num(r.volume, 0),
             "color": up if r.close >= r.open else down} for r in df.itertuples()]


def series_to_line(df: pd.DataFrame, column: str) -> list:
    """Une entrée par barre : les valeurs manquantes (préchauffage) deviennent des
    points "vides" ({time} seul) afin que tous les graphiques gardent exactement les
    mêmes positions et restent synchronisés."""
    out = []
    for t, v in zip(df["timestamp"], df[column]):
        val = _num(v)
        out.append({"time": _day(t)} if val is None else {"time": _day(t), "value": val})
    return out


_REASON = {"SL": "Stop", "TP": "Objectif", "SIGNAL": "Signal", "END_OF_DATA": "Fin"}


def trades_to_markers(trades: pd.DataFrame) -> list:
    """Flèches d'achat (vertes, sous la bougie) et de vente (rouges, au-dessus), triées par date."""
    markers = []
    for t in trades.itertuples():
        markers.append({"time": _day(t.entry_time), "position": "belowBar",
                        "color": THEME["up"], "shape": "arrowUp", "text": "Achat"})
        sign = "+" if t.pnl_dollars >= 0 else "−"
        markers.append({"time": _day(t.exit_time), "position": "aboveBar",
                        "color": THEME["down"], "shape": "arrowDown",
                        "text": f"{_REASON.get(t.exit_reason, t.exit_reason)} {sign}{abs(t.pnl_dollars):.0f}$"})
    markers.sort(key=lambda m: m["time"])
    return markers


def projection_candles(candles: list) -> list:
    """Bougies projetées (une par mois), en ambre translucide pour ne jamais les
    confondre avec de vraies bougies."""
    out = []
    for c in candles:
        out.append({**c, "color": "rgba(245,158,11,0.35)", "borderColor": THEME["proj"],
                    "wickColor": THEME["proj"]})
    return out


# Fonction JS réutilisable : dessine (ou redessine) un graphique prix + RSI optionnel.
# Utilisée par la page à un seul graphique (build_chart_html) ET par la page d'aperçu interactive.
RENDER_JS = """
window.renderTV = function (P, T, els) {
  const LC = window.LightweightCharts;
  els.legend.textContent = '';
  if (!LC) {
    els.legend.textContent = 'Bibliothèque graphique non chargée (connexion internet requise).';
    return { destroy: function () {}, resize: function () {} };
  }
  const base = {
    layout: { background: { type: 'solid', color: T.bg }, textColor: T.text },
    grid: { vertLines: { color: T.grid }, horzLines: { color: T.grid } },
    rightPriceScale: { borderColor: T.grid },
    timeScale: { borderColor: T.grid, rightOffset: 4 },
    crosshair: { mode: LC.CrosshairMode.Normal },
  };
  const mainEl = els.main;
  // Logo d'attribution TradingView intégré (option attributionLogo, disponible depuis la v4.2.0)
  const main = LC.createChart(mainEl, Object.assign({ width: mainEl.clientWidth, height: mainEl.clientHeight }, base,
    { layout: Object.assign({}, base.layout, { attributionLogo: true }) }));

  const candles = main.addCandlestickSeries({
    upColor: T.up, downColor: T.down, wickUpColor: T.up, wickDownColor: T.down, borderVisible: false,
  });
  candles.setData(P.candles);
  if (P.markers && P.markers.length) candles.setMarkers(P.markers);

  if (P.volume && P.volume.length) {
    const vol = main.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol' });
    main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(P.volume);
  }
  (P.overlays || []).forEach(function (o) {
    const s = main.addLineSeries({ color: o.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    s.setData(o.data);
  });

  const charts = [main], rsiEl = els.rsi;
  const withRsi = !!(P.rsi && P.rsi.length && rsiEl);
  if (els.rsilabel) els.rsilabel.style.display = withRsi ? 'block' : 'none';
  if (rsiEl) rsiEl.style.display = withRsi ? 'block' : 'none';
  if (withRsi) {
    const rsiChart = LC.createChart(rsiEl, Object.assign({ width: rsiEl.clientWidth, height: rsiEl.clientHeight }, base));
    const line = rsiChart.addLineSeries({
      color: T.rsi, lineWidth: 2, priceLineVisible: false,
      autoscaleInfoProvider: function () { return { priceRange: { minValue: 0, maxValue: 100 } }; },
    });
    line.setData(P.rsi);
    [30, 70].forEach(function (lvl) {
      line.createPriceLine({ price: lvl, color: '#64748b', lineWidth: 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true, title: '' });
    });
    charts.push(rsiChart);
  }

  // Défilement / zoom synchronisés entre le prix et le RSI
  let busy = false;
  charts.forEach(function (src) {
    src.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
      if (busy || !range) return;
      busy = true;
      charts.forEach(function (dst) { if (dst !== src) dst.timeScale().setVisibleLogicalRange(range); });
      busy = false;
    });
  });
  charts.forEach(function (c) { c.timeScale().fitContent(); });

  // Légende façon TradingView : titre + OHLC sous le curseur
  const last = P.candles.length ? P.candles[P.candles.length - 1] : null;
  function fmt(x) { return (typeof x === 'number') ? x.toFixed(2) : '–'; }
  function show(d) {
    els.legend.textContent = '';
    const b = document.createElement('b'); b.textContent = P.title || ''; els.legend.appendChild(b);
    if (d) els.legend.appendChild(document.createTextNode('  O ' + fmt(d.open) + '  H ' + fmt(d.high) + '  L ' + fmt(d.low) + '  C ' + fmt(d.close)));
  }
  show(last);
  main.subscribeCrosshairMove(function (param) {
    const d = param && param.seriesData ? param.seriesData.get(candles) : null;
    show(d || last);
  });

  return {
    destroy: function () { charts.forEach(function (c) { c.remove(); }); },
    resize: function () {
      charts.forEach(function (c, i) { var el = (i === 0 ? mainEl : rsiEl); c.applyOptions({ width: el.clientWidth, height: el.clientHeight }); });
    },
  };
};
"""


def build_chart_html(payload: dict, height_main: int = 430, height_rsi: int = 150) -> str:
    """payload : title, candles, [volume], [overlays: [{name,color,data}]], [markers],
    [rsi]. Retourne une page HTML autonome (à passer à streamlit.components.v1.html)."""
    data = json.dumps({**payload, "theme": THEME}, ensure_ascii=False).replace("<", "\\u003c")
    return (_TEMPLATE
            .replace("__LWC_URL__", LWC_URL)
            .replace("__RENDER_JS__", RENDER_JS)
            .replace("__PAYLOAD__", data)
            .replace("__H_MAIN__", str(int(height_main)))
            .replace("__H_RSI__", str(int(height_rsi)))
            .replace("__BG__", THEME["bg"]).replace("__TEXT__", THEME["text"]))


_TEMPLATE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin:0; background:__BG__; color:__TEXT__; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; }
  #wrap { position:relative; }
  #legend { position:absolute; top:8px; left:10px; z-index:5; font-size:12px; line-height:1.5; pointer-events:none; }
  #legend b { color:#e6edf7; font-size:13px; }
  #main { height:__H_MAIN__px; }
  #rsi { height:__H_RSI__px; margin-top:2px; }
  #rsilabel { font-size:11px; padding:4px 10px 0; }
  #attr { font-size:11px; padding:6px 10px 8px; opacity:.85; }
  #attr a { color:#7aa2ff; text-decoration:none; }
</style></head><body>
<div id="wrap"><div id="legend"></div><div id="main"></div></div>
<div id="rsilabel" style="display:none">RSI (14) — surachat au-dessus de 70, survente en dessous de 30</div>
<div id="rsi" style="display:none"></div>
<div id="attr">Graphiques : <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a> · Copyright © TradingView, Inc.</div>
<script src="__LWC_URL__"></script>
<script>__RENDER_JS__</script>
<script>
(function () {
  const P = __PAYLOAD__;
  const h = window.renderTV(P, P.theme, {
    main: document.getElementById('main'), rsi: document.getElementById('rsi'),
    rsilabel: document.getElementById('rsilabel'), legend: document.getElementById('legend'),
  });
  window.addEventListener('resize', function () { h.resize(); });
})();
</script></body></html>
"""
