"""
StrategyLab — application web 100 % Python (Streamlit), dans le style de TradingView.

Python fait TOUT : récupération des données de marché, indicateurs, backtest, projection ET interface.
Le graphique est la bibliothèque TradingView Lightweight Charts. Aucun serveur à relier, aucune adresse à saisir.

Lancer : streamlit run ui/streamlit_app.py     (ou, en version un seul fichier : streamlit run app.py)
Simulateur : aucun ordre réel. Un backtest ne garantit jamais la performance future.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # lancement local depuis le projet complet

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config.settings import (
    FIREBASE_PROJECT_ID, FIREBASE_WEB_API_KEY, DEFAULT_COMMISSION_RATE, DEFAULT_INITIAL_CASH, DEFAULT_RISK_PCT, DEFAULT_SLIPPAGE_RATE,
    DEFAULT_STOP_LOSS_PCT, DEFAULT_TAKE_PROFIT_PCT, STANDARD_PERIODS,
)
from data.live_providers import DataUnavailable, LiveDataProvider
from ui import app_logic as logic
from ui import tv_chart

st.set_page_config(page_title="StrategyLab", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.stApp { background:#131722; color:#d1d4dc; }
[data-testid="stHeader"] { background:#131722; }
[data-testid="stSidebar"] { background:#1e222d; border-right:1px solid #2a2e39; }
.block-container { padding-top:1.2rem; max-width:none; }
h1, h2, h3, h4, label, p, span { color:inherit; }
[data-testid="stMetric"] { background:#1e222d; border-radius:4px; padding:8px 12px; }
[data-testid="stMetricLabel"] { color:#787b86; }
.stTabs [data-baseweb="tab"] { color:#787b86; } .stTabs [aria-selected="true"] { color:#d1d4dc; }
[data-testid="stRadio"] [role="radiogroup"] { gap:4px; }
.sl-title { font-size:20px; font-weight:700; } .sl-sub { color:#787b86; font-size:12px; }
</style>""", unsafe_allow_html=True)

ASSET_LABELS = {"OIL": "Pétrole (WTI)", "GOLD": "Or (XAU/USD)"}
PERIOD_ORDER = ["3D", "1M", "4M", "1Y", "3Y", "5Y", "10Y", "CUSTOM"]
PERIOD_SHORT = {"3D": "3J", "1M": "1M", "4M": "4M", "1Y": "1A", "3Y": "3A", "5Y": "5A", "10Y": "10A", "CUSTOM": "Perso."}
REASONS = {"SL": "Stop", "TP": "Objectif", "SIGNAL": "Signal", "END_OF_DATA": "Fin"}
DEFAULT_BUY = [("RSI (14)", "<", "Valeur", 30.0, "Prix"), ("Prix", ">", "Indicateur", 0.0, "SMA 200")]
DEFAULT_SELL = [("RSI (14)", ">", "Valeur", 70.0, "Prix"), ("Prix", "<", "Indicateur", 0.0, "SMA 200")]


def _secret(name: str):
    try:
        value = st.secrets.get(name)
    except Exception:  # aucun fichier de secrets configuré
        value = None
    return value or os.environ.get(name)


@st.cache_resource
def get_provider() -> LiveDataProvider:
    # Un seul fournisseur partagé : une récupération par heure pour tous les visiteurs.
    return LiveDataProvider(
        twelvedata_api_key=_secret("TWELVEDATA_API_KEY"), fred_api_key=_secret("FRED_API_KEY"), ttl_seconds=3600,
        firebase_project=_secret("FIREBASE_PROJECT_ID") or FIREBASE_PROJECT_ID,
        firebase_api_key=_secret("FIREBASE_API_KEY") or FIREBASE_WEB_API_KEY)


@st.cache_data(ttl=3600, show_spinner="Analyse en cours…")
def analyse(asset, period_key, c_start, c_end, cash, risk, sl, tp, com, slip, buy_json, sell_json):
    res = logic.run_analysis(get_provider().get_ohlcv(asset), period_key, json.loads(buy_json), json.loads(sell_json),
                             cash, risk, sl, tp, com, slip, ASSET_LABELS[asset], c_start, c_end)
    res["extra"] = logic.summarize(res, sl, slip)
    return res


@st.cache_data(ttl=3600, show_spinner="Calcul de la projection…")
def projection(asset):
    return logic.projection_view(get_provider().get_ohlcv(asset), ASSET_LABELS[asset])


def money(v, d=2):
    return f"{v:,.{d}f}".replace(",", " ")


def signed(v, d=2, suffix=""):
    return f"{'+' if v >= 0 else '−'}{money(abs(v), d)}{suffix}"


def rule_builder(prefix: str, defaults: list) -> dict:
    n = st.number_input("Nombre de conditions", 1, 5, len(defaults), key=f"{prefix}_n")
    combo = st.radio("Logique", ["AND", "OR"], horizontal=True, key=f"{prefix}_logic",
                     format_func=lambda x: "ET" if x == "AND" else "OU")
    names = list(logic.INDICATOR_CHOICES)
    conditions = []
    for i in range(int(n)):
        d = defaults[i] if i < len(defaults) else ("Prix", ">", "Valeur", 0.0, "SMA 200")
        left = st.selectbox("Indicateur", names, index=names.index(d[0]), key=f"{prefix}_l{i}")
        c1, c2 = st.columns([1, 2])
        op = c1.selectbox("Op.", logic.OPERATORS, index=logic.OPERATORS.index(d[1]), key=f"{prefix}_o{i}")
        mode = c2.radio("Comparer à", ["Valeur", "Indicateur"], index=0 if d[2] == "Valeur" else 1,
                        key=f"{prefix}_m{i}", horizontal=True)
        if mode == "Valeur":
            conditions.append(logic.make_condition(left, op, mode, value=st.number_input("Seuil", value=float(d[3]), key=f"{prefix}_v{i}")))
        else:
            right = st.selectbox("Indicateur de comparaison", names, index=names.index(d[4]), key=f"{prefix}_r{i}")
            conditions.append(logic.make_condition(left, op, mode, right_label=right))
        if i < int(n) - 1:
            st.caption("— ET —" if combo == "AND" else "— OU —")
    return logic.make_rule(combo, conditions)


def rule_text(rule: dict) -> str:
    sep = " ET " if rule["logic"] == "AND" else " OU "
    parts = []
    for c in rule["conditions"]:
        right = c["right"] if isinstance(c["right"], (int, float)) else _spec_name(c["right"])
        parts.append(f"{_spec_name(c['left'])} {c['operator']} {right}")
    return sep.join(parts)


def _spec_name(spec: dict) -> str:
    for label, s in logic.INDICATOR_CHOICES.items():
        if s == spec:
            return label
    return spec["name"]


def show_chart(payload: dict, height_main: int, height_rsi: int = 130):
    components.html(tv_chart.build_chart_html(payload, height_main=height_main, height_rsi=height_rsi),
                    height=logic.chart_height(payload, height_main, height_rsi), scrolling=False)


# ------------------------------------------------------------------ données réelles
provider = get_provider()
markets, unavailable = {}, {}
for key in ASSET_LABELS:
    try:
        df = provider.get_ohlcv(key)
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        markets[key] = {"last": last, "chg": (last / prev - 1) * 100, **provider.info(key)}
    except DataUnavailable as exc:
        unavailable[key] = str(exc)
if not markets:
    st.error("Aucune donnée de marché disponible pour le moment. La raison exacte est affichée ci-dessous "
             "(envoie-la telle quelle pour qu'on corrige).")
    for k, reason in unavailable.items():
        st.code(f"{ASSET_LABELS[k]} : {reason}")
    st.stop()

# ------------------------------------------------------------------ panneau de gauche : liste de suivi + stratégie
with st.sidebar:
    st.markdown("### 📈 StrategyLab")
    st.caption("Testez votre stratégie sur l'historique du marché")
    st.markdown("**Liste de suivi**")
    asset = st.radio("Actif", list(markets), label_visibility="collapsed",
                     format_func=lambda k: f"{ASSET_LABELS[k]}   {money(markets[k]['last'])}   ({markets[k]['chg']:+.2f} %)")
    for k, reason in unavailable.items():
        st.caption(f"{ASSET_LABELS[k]} : indisponible. {reason}")
    st.markdown("**Stratégie**")
    tab_buy, tab_sell = st.tabs(["Entrée Achat", "Entrée Vente"])
    with tab_buy:
        buy_rule = rule_builder("buy", DEFAULT_BUY)
    with tab_sell:
        sell_rule = rule_builder("sell", DEFAULT_SELL)
    st.markdown("**Capital & risque**")
    a1, a2 = st.columns(2)
    cash = a1.number_input("Capital ($)", value=DEFAULT_INITIAL_CASH, min_value=100.0, step=100.0)
    risk_pct = a2.number_input("Risque / trade (%)", value=DEFAULT_RISK_PCT * 100, min_value=0.01, max_value=100.0)
    b1, b2 = st.columns(2)
    sl_pct = b1.number_input("Stop loss (%)", value=DEFAULT_STOP_LOSS_PCT * 100, min_value=0.05, max_value=99.0)
    tp_pct = b2.number_input("Take profit (%)", value=DEFAULT_TAKE_PROFIT_PCT * 100, min_value=0.05, max_value=500.0)
    c1, c2 = st.columns(2)
    commission = c1.number_input("Commission (%)", value=DEFAULT_COMMISSION_RATE * 100, min_value=0.0, max_value=5.0, step=0.01)
    slippage = c2.number_input("Slippage (%)", value=DEFAULT_SLIPPAGE_RATE * 100, min_value=0.0, max_value=5.0, step=0.01)
    st.caption("Taille de position calculée selon le risque (capital × risque ÷ distance du stop). "
               "Les résultats passés ne garantissent pas les performances futures.")

# ------------------------------------------------------------------ en-tête : actif + périodes
info = markets[asset]
st.markdown(f"<span class='sl-title'>{ASSET_LABELS[asset]}</span> <span class='sl-sub'>· 1J · données jusqu'au "
            f"{info.get('last_date')} · {info.get('source')} · actualisation automatique</span>", unsafe_allow_html=True)
st.caption("Panneau de gauche : actif, stratégie, capital et risque (sur téléphone, touchez la flèche › en haut à gauche pour "
           "l'ouvrir). Tout se recalcule automatiquement à chaque changement.")
period_key = st.radio("Période", PERIOD_ORDER, index=PERIOD_ORDER.index("5Y"), horizontal=True, label_visibility="collapsed",
                      format_func=lambda k: PERIOD_SHORT[k])
c_start = c_end = None
if period_key == "CUSTOM":
    last_day = pd.Timestamp(info["last_date"])
    d1, d2, _ = st.columns([1, 1, 4])
    c_start = d1.date_input("Début", value=(last_day - pd.Timedelta(days=365)).date()).isoformat()
    c_end = d2.date_input("Fin", value=last_day.date()).isoformat()

# ------------------------------------------------------------------ analyse (Python) et affichage
try:
    res = analyse(asset, period_key, c_start, c_end, cash, risk_pct / 100, sl_pct / 100, tp_pct / 100,
                  commission / 100, slippage / 100, json.dumps(buy_rule), json.dumps(sell_rule))
except (ValueError, DataUnavailable) as exc:
    st.error(str(exc))
    st.stop()

rep, extra = res["report"], res["extra"]
if not rep["reliable_sample"]:
    st.warning(f"Échantillon faible ({rep['n_trades']} trade{'s' if rep['n_trades'] > 1 else ''}) : à interpréter avec prudence, "
               "trop peu de trades pour une lecture statistique fiable.")
if info.get("stale_error"):
    st.warning(f"Mise à jour des données impossible ({info['stale_error']}) : dernière copie connue utilisée.")
if info.get("ohlc_approx"):
    st.info("Cet actif ne fournit que la clôture du jour : bougies reconstruites (pas de vraies mèches), indicateurs de volume désactivés.")

show_chart(res["chart_payload"], height_main=470)

t_over, t_perf, t_trades, t_props, t_proj = st.tabs(["Aperçu", "Résumé de la performance", "Liste des trades", "Propriétés", "Projection"])
pnl = rep["final_equity"] - rep["initial_cash"]
pf = "∞" if rep["profit_factor"] == float("inf") else ("—" if rep["profit_factor"] is None else f"{rep['profit_factor']:.2f}")
with t_over:
    k = st.columns(5)
    k[0].metric("P&L total", signed(pnl, 2, " $"), delta=f"{rep['return_pct']:+.2f} %")
    k[1].metric("Drawdown maximal", f"{rep['max_drawdown_pct']:.2f} %")
    k[2].metric("Nombre de trades", rep["n_trades"], delta=f"{rep['n_wins']} gagnants · {rep['n_losses']} perdants", delta_color="off")
    k[3].metric("Trades gagnants", f"{rep['win_rate_pct']:.1f} %" if rep["n_trades"] else "—")
    k[4].metric("Profit factor", pf)
    st.area_chart(res["equity"].set_index("timestamp")["equity"], height=220)
with t_perf:
    rows = [
        ("Capital initial", f"{money(rep['initial_cash'])} $"), ("Capital final", f"{money(rep['final_equity'])} $"),
        ("P&L total", signed(pnl, 2, " $")), ("Rendement", signed(rep["return_pct"], 2, " %")),
        ("Drawdown maximal", f"{rep['max_drawdown_pct']:.2f} %"), ("Nombre de trades", str(rep["n_trades"])),
        ("Trades gagnants", str(rep["n_wins"])), ("Trades perdants", str(rep["n_losses"])),
        ("Taux de réussite", f"{rep['win_rate_pct']:.2f} %" if rep["n_trades"] else "—"),
        ("Gain moyen par trade", signed(rep["avg_win_dollars"], 2, " $") if rep["n_wins"] else "—"),
        ("Perte moyenne par trade", signed(rep["avg_loss_dollars"], 2, " $") if rep["n_losses"] else "—"),
        ("Espérance par trade", signed(rep["expectancy_dollars"], 2, " $") if rep["n_trades"] else "—"),
        ("Profit factor", pf),
        ("Ratio de Sharpe (annualisé, 252 séances)", "—" if extra["sharpe_ratio"] is None else f"{extra['sharpe_ratio']:.2f}"),
        ("Durée moyenne d'un trade (séances)", f"{rep['avg_trade_duration_bars']:.1f}" if rep["n_trades"] else "—"),
        ("Frais de transaction", f"{money(rep['total_fees_dollars'])} $"),
        ("Slippage estimé", f"{money(extra['slippage_estimated_dollars'])} $"),
    ] + [(f"Sorties : {REASONS.get(r, r)}", str(n)) for r, n in extra["exit_reasons"].items()]
    st.table(pd.DataFrame(rows, columns=["Indicateur", "Valeur"]).set_index("Indicateur"))
with t_trades:
    if not extra["trade_rows"]:
        st.write("Aucun trade sur cette configuration.")
    else:
        tr = pd.DataFrame(extra["trade_rows"]).rename(columns={
            "entry": "Entrée", "exit": "Sortie", "entry_price": "Prix entrée", "exit_price": "Prix sortie", "quantity": "Quantité",
            "pnl": "Résultat ($)", "pnl_pct": "Résultat (%)", "r": "R", "reason": "Raison"})
        tr["Raison"] = tr["Raison"].map(lambda r: REASONS.get(r, r))
        st.dataframe(tr)
        st.download_button("Exporter (CSV)", tr.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name="strategylab_trades.csv", mime="text/csv")
with t_props:
    props = [("Actif", ASSET_LABELS[asset]), ("Période", rep["period"]), ("Capital initial", f"{money(cash)} $"),
             ("Risque par trade", f"{risk_pct:.2f} %"), ("Stop loss", f"{sl_pct:.2f} %"), ("Take profit", f"{tp_pct:.2f} %"),
             ("Commission", f"{commission:.2f} %"), ("Slippage", f"{slippage:.2f} %"),
             ("Règle d'achat", rule_text(buy_rule)), ("Règle de vente", rule_text(sell_rule)),
             ("Source des données", str(info.get("source"))), ("Dernière date", str(info.get("last_date")))]
    st.table(pd.DataFrame(props, columns=["Paramètre", "Valeur"]).set_index("Paramètre"))
with t_proj:
    try:
        view = projection(asset)
        st.caption("Plage de probabilité issue de la volatilité historique : "
                   f"{view['n_paths']} trajectoires simulées, même dispersion que par le passé, aucune tendance supposée. "
                   "Ce n'est PAS une prédiction. Bougies pleines = historique réel ; bougies orange = plage simulée (une par mois).")
        show_chart(view["payload"], height_main=360)
        st.table(pd.DataFrame(view["table"]).rename(columns={
            "echeance": "Échéance", "date": "Date", "p10": "10e percentile", "mediane": "Médiane", "p90": "90e percentile"}).set_index("Échéance"))
    except ValueError as exc:
        st.info(str(exc))

st.caption(rep["disclaimer"])
