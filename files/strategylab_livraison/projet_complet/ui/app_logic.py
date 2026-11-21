"""
Logique de l'application, SANS Streamlit (donc testable sans interface).
L'écran Streamlit (ui/streamlit_app.py) ne fait que l'afficher.
"""
import math

import pandas as pd

from analysis.projection import monte_carlo_projection
from backtest.engine import BacktestEngine
from config.settings import SLTP_AMBIGUITY_POLICY, STANDARD_PERIODS
from data.periods import resolve_period
from indicators.base import IndicatorEngine
from metrics.report import build_report
from risk.manager import RiskParams
from strategy.builder import StrategyBuilder
from ui import tv_chart

OPERATORS = [">", "<", ">=", "<=", "="]


def _spec(name, **params):
    return {"name": name, "params": params}


INDICATOR_CHOICES = {
    "Prix": _spec("PRICE"),
    "RSI (14)": _spec("RSI", window=14),
    "SMA 20": _spec("SMA", window=20), "SMA 50": _spec("SMA", window=50), "SMA 200": _spec("SMA", window=200),
    "EMA 12": _spec("EMA", window=12), "EMA 26": _spec("EMA", window=26),
    "Variation % (5 jours)": _spec("PCT_CHANGE", periods=5),
    "MACD ligne": _spec("MACD_LINE"), "MACD signal": _spec("MACD_SIGNAL"), "MACD histogramme": _spec("MACD_HIST"),
    "Stochastique %K": _spec("STOCH_K"), "Stochastique %D": _spec("STOCH_D"),
    "Williams %R": _spec("WILLIAMS_R", window=14), "CCI (20)": _spec("CCI", window=20),
    "ADX (14)": _spec("ADX", window=14), "Aroon haut": _spec("AROON_UP", window=25),
    "Aroon bas": _spec("AROON_DOWN", window=25), "ROC (12)": _spec("ROC", window=12),
    "Momentum (10)": _spec("MOMENTUM", window=10), "TRIX (15)": _spec("TRIX", window=15),
    "Ultimate Oscillator": _spec("ULTIMATE_OSC"), "ATR (14)": _spec("ATR", window=14),
    "Bollinger haute": _spec("BB_UPPER", window=20), "Bollinger basse": _spec("BB_LOWER", window=20),
    "Bollinger largeur %": _spec("BB_BANDWIDTH", window=20),
    "Donchian haut": _spec("DONCHIAN_UPPER", window=20), "Donchian bas": _spec("DONCHIAN_LOWER", window=20),
    "Keltner haut": _spec("KELTNER_UPPER"), "Keltner bas": _spec("KELTNER_LOWER"),
    "Écart-type (20)": _spec("STDDEV", window=20),
    "Volume": _spec("VOLUME"), "OBV": _spec("OBV"), "VWAP (20)": _spec("VWAP", window=20),
    "MFI (14)": _spec("MFI", window=14), "CMF (20)": _spec("CMF", window=20),
}


def make_condition(left_label: str, operator: str, mode: str, value=None, right_label: str | None = None) -> dict:
    """mode = 'Valeur' (seuil numérique) ou 'Indicateur' (comparaison à un autre indicateur)."""
    if left_label not in INDICATOR_CHOICES:
        raise ValueError(f"Indicateur inconnu: {left_label}")
    if operator not in OPERATORS:
        raise ValueError(f"Opérateur inconnu: {operator}")
    if mode == "Valeur":
        if value is None:
            raise ValueError("Un seuil numérique est requis.")
        right = float(value)
    elif mode == "Indicateur":
        if right_label not in INDICATOR_CHOICES:
            raise ValueError(f"Indicateur de comparaison inconnu: {right_label}")
        right = INDICATOR_CHOICES[right_label]
    else:
        raise ValueError(f"Mode inconnu: {mode}")
    return {"left": INDICATOR_CHOICES[left_label], "operator": operator, "right": right}


def make_rule(logic: str, conditions: list) -> dict:
    return {"logic": logic, "conditions": conditions}


def run_analysis(full_df: pd.DataFrame, period_key: str, buy_rule: dict, sell_rule: dict,
                 cash: float, risk_pct: float, stop_loss_pct: float, take_profit_pct: float,
                 commission_rate: float, slippage_rate: float, asset_label: str = "",
                 custom_start=None, custom_end=None) -> dict:
    df = full_df.copy()

    # Indicateurs d'affichage ET signaux calculés sur TOUT l'historique, puis découpe de
    # la période : un indicateur long (SMA 200) reste donc défini même sur une période courte.
    ind = IndicatorEngine(df)
    df["SMA20"] = ind.get(_spec("SMA", window=20))
    df["SMA50"] = ind.get(_spec("SMA", window=50))
    df["RSI14"] = ind.get(_spec("RSI", window=14))
    df = StrategyBuilder(buy_rule, sell_rule).apply(df)
    period_df = resolve_period(df, period_key, custom_start, custom_end)

    risk = RiskParams(risk_pct, stop_loss_pct, take_profit_pct)
    bt = BacktestEngine(cash, risk, commission_rate, slippage_rate, SLTP_AMBIGUITY_POLICY)
    trades, equity = bt.run(period_df)
    report = build_report(trades, equity, cash, asset_label, STANDARD_PERIODS[period_key]["label"],
                          commission_rate, slippage_rate)

    payload = {
        "title": f"{asset_label} · {STANDARD_PERIODS[period_key]['label']}",
        "candles": tv_chart.df_to_candles(period_df),
        "volume": tv_chart.df_to_volume(period_df),
        "overlays": [
            {"name": "SMA 20", "color": tv_chart.THEME["sma_fast"], "data": tv_chart.series_to_line(period_df, "SMA20")},
            {"name": "SMA 50", "color": tv_chart.THEME["sma_slow"], "data": tv_chart.series_to_line(period_df, "SMA50")},
        ],
        "markers": tv_chart.trades_to_markers(trades),
        "rsi": tv_chart.series_to_line(period_df, "RSI14"),
    }
    return {"period_df": period_df, "trades": trades, "equity": equity, "report": report,
            "chart_payload": payload}


def projection_view(full_df: pd.DataFrame, title: str, n_history: int = 90, n_months: int = 12) -> dict:
    proj = monte_carlo_projection(full_df, n_months=n_months)
    history = tv_chart.df_to_candles(full_df.tail(n_history))
    payload = {"title": f"{title} · projection statistique", "candles": history + tv_chart.projection_candles(proj.candles)}
    return {"payload": payload, "table": proj.table, "sigma_daily": proj.sigma_daily,
            "n_paths": proj.n_paths, "seed": proj.seed}


def chart_height(payload: dict, height_main: int = 430, height_rsi: int = 150) -> int:
    """Hauteur totale à réserver pour le composant HTML (prix + RSI éventuel + légendes)."""
    return height_main + (height_rsi + 24 if payload.get("rsi") else 0) + 40


def summarize(res: dict, stop_loss_pct: float, slippage_rate: float) -> dict:
    """Chiffres complémentaires à build_report : ratio de Sharpe (annualisé sur 252 séances), slippage
    estimé en dollars, sorties par type et lignes de trades avec leur multiple de risque R
    (résultat ÷ risque au stop). Partagé par l'API et l'application Streamlit."""
    trades, equity = res["trades"], res["equity"]
    returns = equity["equity"].pct_change().dropna()
    sharpe = (float(returns.mean() / returns.std() * math.sqrt(252)) if len(returns) > 2 and returns.std() > 0 else None)
    rows, reasons, slip_cost = [], {}, 0.0
    for t in trades.itertuples():
        risk_at_stop = t.quantity * t.entry_price * stop_loss_pct
        rows.append({
            "entry": pd.Timestamp(t.entry_time).strftime("%Y-%m-%d"), "exit": pd.Timestamp(t.exit_time).strftime("%Y-%m-%d"),
            "entry_price": round(float(t.entry_price), 4), "exit_price": round(float(t.exit_price), 4),
            "quantity": round(float(t.quantity), 4), "pnl": round(float(t.pnl_dollars), 2),
            "pnl_pct": round(float(t.pnl_pct), 2), "reason": str(t.exit_reason),
            "r": round(float(t.pnl_dollars) / risk_at_stop, 2) if risk_at_stop > 0 else None,
        })
        reasons[str(t.exit_reason)] = reasons.get(str(t.exit_reason), 0) + 1
        slip_cost += slippage_rate * t.quantity * (t.entry_price + t.exit_price)
    return {"sharpe_ratio": sharpe, "slippage_estimated_dollars": round(slip_cost, 2), "exit_reasons": reasons, "trade_rows": rows}
