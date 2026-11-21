import pandas as pd

from indicators.base import IndicatorEngine
from strategy.rules import evaluate_rule


class StrategyBuilder:
    """Construit les colonnes buy_signal / sell_signal à partir de règles
    déclaratives. N'exécute rien — c'est le rôle du backtest engine.

    Exemple (correspond à celui du cahier des charges):
        buy_rule = {
            "logic": "AND",
            "conditions": [
                {"left": {"name": "RSI", "params": {"window": 14}},
                 "operator": "<", "right": 30},
                {"left": {"name": "PRICE"}, "operator": ">",
                 "right": {"name": "SMA", "params": {"window": 200}}},
            ],
        }
    """

    def __init__(self, buy_rule: dict, sell_rule: dict):
        self.buy_rule = buy_rule
        self.sell_rule = sell_rule

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        engine = IndicatorEngine(df)
        out = df.copy()
        out["buy_signal"] = evaluate_rule(engine, self.buy_rule)
        out["sell_signal"] = evaluate_rule(engine, self.sell_rule)
        return out
