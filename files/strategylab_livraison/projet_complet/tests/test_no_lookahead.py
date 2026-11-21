import numpy as np
import pandas as pd

from strategy.builder import StrategyBuilder


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"),
        "open": closes, "high": closes, "low": closes, "close": closes,
    })


BUY_RULE = {
    "logic": "AND",
    "conditions": [
        {"left": {"name": "SMA", "params": {"window": 3}}, "operator": ">",
         "right": {"name": "SMA", "params": {"window": 5}}},
    ],
}
SELL_RULE = {
    "logic": "AND",
    "conditions": [
        {"left": {"name": "SMA", "params": {"window": 3}}, "operator": "<",
         "right": {"name": "SMA", "params": {"window": 5}}},
    ],
}


def test_changing_future_bars_does_not_change_past_signals():
    rng = np.random.default_rng(0)
    base = list(100 + np.cumsum(rng.normal(0, 1, 40)))

    builder = StrategyBuilder(BUY_RULE, SELL_RULE)
    out_a = builder.apply(_df(base))

    # on modifie fortement uniquement la toute fin de la série
    modified = base.copy()
    modified[-5:] = [modified[-6] * 5] * 5
    out_b = builder.apply(_df(modified))

    # les signaux calculés AVANT le point de modification doivent être identiques
    cut = len(base) - 10
    pd.testing.assert_series_equal(
        out_a["buy_signal"].iloc[:cut], out_b["buy_signal"].iloc[:cut], check_names=False
    )
    pd.testing.assert_series_equal(
        out_a["sell_signal"].iloc[:cut], out_b["sell_signal"].iloc[:cut], check_names=False
    )
