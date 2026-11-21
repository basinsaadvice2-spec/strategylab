"""
Point d'entrée V1 (sans interface graphique): choisit un actif, une période,
une stratégie déclarative et des paramètres de risque, lance le backtest et
affiche le rapport. C'est ce que l'écran Streamlit (ui/streamlit_app.py)
appelle en coulisses.
"""
import argparse
import logging
import json
from pathlib import Path

from config.settings import (
    ASSETS, DEFAULT_INITIAL_CASH, DEFAULT_RISK_PCT, DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT, DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE_RATE,
    SLTP_AMBIGUITY_POLICY, STANDARD_PERIODS,
)
from data.provider import CSVDataProvider
from data.periods import resolve_period
from strategy.builder import StrategyBuilder
from risk.manager import RiskParams
from backtest.engine import BacktestEngine
from metrics.report import build_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Stratégie d'exemple tirée telle quelle du cahier des charges:
# ACHAT: RSI < 30 ET prix > SMA 200
# VENTE: RSI > 70 ET prix < SMA 200
EXAMPLE_BUY_RULE = {
    "logic": "AND",
    "conditions": [
        {"left": {"name": "RSI", "params": {"window": 14}}, "operator": "<", "right": 30},
        {"left": {"name": "PRICE"}, "operator": ">",
         "right": {"name": "SMA", "params": {"window": 200}}},
    ],
}
EXAMPLE_SELL_RULE = {
    "logic": "AND",
    "conditions": [
        {"left": {"name": "RSI", "params": {"window": 14}}, "operator": ">", "right": 70},
        {"left": {"name": "PRICE"}, "operator": "<",
         "right": {"name": "SMA", "params": {"window": 200}}},
    ],
}


def run(asset: str, period_key: str, initial_cash: float, risk_pct: float,
        stop_loss_pct: float, take_profit_pct: float, commission_rate: float,
        slippage_rate: float, buy_rule: dict, sell_rule: dict,
        base_dir: str = "."):
    provider = CSVDataProvider(ASSETS, base_dir=base_dir)
    df = provider.get_ohlcv(asset)

    # Les indicateurs sont calculés sur TOUT l'historique, puis on découpe la
    # période : sinon un indicateur long (ex. SMA 200) resterait vide sur une
    # période courte. Aucun look-ahead : chaque signal n'utilise que le passé.
    builder = StrategyBuilder(buy_rule, sell_rule)
    df = builder.apply(df)
    df = resolve_period(df, period_key)

    risk = RiskParams(risk_pct, stop_loss_pct, take_profit_pct)
    engine = BacktestEngine(initial_cash, risk, commission_rate, slippage_rate,
                             SLTP_AMBIGUITY_POLICY)
    trades, equity = engine.run(df)

    period_label = STANDARD_PERIODS[period_key]["label"]
    report = build_report(trades, equity, initial_cash, asset, period_label,
                           commission_rate, slippage_rate)
    return report, trades, equity


def main():
    p = argparse.ArgumentParser(description="StrategyLab V1 — backtest en ligne de commande")
    p.add_argument("--asset", default="GOLD", choices=list(ASSETS))
    p.add_argument("--period", default="5Y", choices=list(STANDARD_PERIODS))
    p.add_argument("--cash", type=float, default=DEFAULT_INITIAL_CASH)
    p.add_argument("--risk-pct", type=float, default=DEFAULT_RISK_PCT)
    p.add_argument("--stop-loss-pct", type=float, default=DEFAULT_STOP_LOSS_PCT)
    p.add_argument("--take-profit-pct", type=float, default=DEFAULT_TAKE_PROFIT_PCT)
    p.add_argument("--commission-rate", type=float, default=DEFAULT_COMMISSION_RATE)
    p.add_argument("--slippage-rate", type=float, default=DEFAULT_SLIPPAGE_RATE)
    p.add_argument("--out-dir", default="reports")
    args = p.parse_args()

    report, trades, equity = run(
        args.asset, args.period, args.cash, args.risk_pct, args.stop_loss_pct,
        args.take_profit_pct, args.commission_rate, args.slippage_rate,
        EXAMPLE_BUY_RULE, EXAMPLE_SELL_RULE,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    trades.to_csv(out_dir / "trades.csv", index=False)
    equity.to_csv(out_dir / "equity_curve.csv", index=False)
    with open(out_dir / "report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info("=== STRATEGYLAB V1 — RAPPORT ===")
    for k, v in report.items():
        logger.info("%s: %s", k, v)
    logger.info("Résultats écrits dans %s/", out_dir)

    if not report["reliable_sample"]:
        logger.warning(
            "Échantillon de trades faible (%d) — interprétation à prendre "
            "avec prudence.", report["n_trades"]
        )


if __name__ == "__main__":
    main()
