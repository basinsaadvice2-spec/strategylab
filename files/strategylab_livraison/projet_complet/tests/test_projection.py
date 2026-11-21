import numpy as np
import pandas as pd
import pytest

from analysis.projection import monte_carlo_projection


def _df(n=1500, seed=3):
    rng = np.random.default_rng(seed)
    ts = pd.bdate_range("2019-01-01", periods=n, tz="UTC")
    return pd.DataFrame({"timestamp": ts, "close": 80 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))})


def test_projection_is_deterministic_with_same_seed():
    a, b = monte_carlo_projection(_df()), monte_carlo_projection(_df())
    assert a.table == b.table and a.candles == b.candles


def test_projection_has_one_candle_per_month_and_four_checkpoints():
    p = monte_carlo_projection(_df())
    assert len(p.candles) == 12 and [r["echeance"] for r in p.table] == ["1 mois", "3 mois", "6 mois", "12 mois"]


def test_projection_bands_widen_with_horizon():
    p = monte_carlo_projection(_df())
    widths = [r["p90"] - r["p10"] for r in p.table]
    assert widths == sorted(widths)


def test_projection_percentiles_are_ordered_and_median_near_last_price_without_drift():
    df = _df()
    p = monte_carlo_projection(df)
    last = float(df["close"].iloc[-1])
    for r in p.table:
        assert r["p10"] < r["mediane"] < r["p90"]
    assert abs(p.table[0]["mediane"] / last - 1) < 0.03     # dérive nulle : pas de direction supposée


def test_projection_candles_are_well_formed():
    for c in monte_carlo_projection(_df()).candles:
        assert c["low"] <= min(c["open"], c["close"]) and c["high"] >= max(c["open"], c["close"])


def test_projection_rejects_short_history():
    with pytest.raises(ValueError, match="60 barres"):
        monte_carlo_projection(_df(n=30))
