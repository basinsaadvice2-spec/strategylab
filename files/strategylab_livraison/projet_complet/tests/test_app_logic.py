import numpy as np
import pandas as pd
import pytest

from indicators.base import IndicatorEngine
from ui import app_logic as L


def _df(n=2000, volume=0.0, seed=11):
    rng = np.random.default_rng(seed)
    ts = pd.bdate_range("2018-01-01", periods=n, tz="UTC")
    c = 70 * np.exp(np.cumsum(rng.normal(0.0002, 0.016, n)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"timestamp": ts, "open": o, "high": np.maximum(o, c), "low": np.minimum(o, c),
                         "close": c, "volume": volume})


RULES = (L.make_rule("AND", [L.make_condition("RSI (14)", "<", "Valeur", 40)]),
         L.make_rule("OR", [L.make_condition("RSI (14)", ">", "Valeur", 60)]))


def test_indicators_are_defined_from_the_first_bar_of_a_short_period():
    res = L.run_analysis(_df(), "4M", *RULES, 10000, .02, .02, .04, .001, .0005, "Pétrole")
    assert pd.notna(res["period_df"]["SMA50"].iloc[0])        # préchauffage fait AVANT la découpe


def test_analysis_returns_everything_the_screen_needs():
    res = L.run_analysis(_df(), "3Y", *RULES, 10000, .02, .02, .04, .001, .0005, "Pétrole")
    assert {"period_df", "trades", "equity", "report", "chart_payload"} <= set(res)
    assert len(res["chart_payload"]["candles"]) == len(res["period_df"]) == len(res["chart_payload"]["rsi"])
    assert len(res["chart_payload"]["markers"]) == 2 * len(res["trades"])


def test_volume_rules_never_fire_on_assets_without_real_volume():
    buy = L.make_rule("AND", [L.make_condition("OBV", ">=", "Valeur", 0)])
    res = L.run_analysis(_df(volume=0.0), "3Y", buy, RULES[1], 10000, .02, .02, .04, .001, .0005, "Pétrole")
    assert len(res["trades"]) == 0


def test_volume_indicators_work_when_real_volume_exists():
    s = IndicatorEngine(_df(volume=1000.0)).get({"name": "OBV"})
    assert s.notna().any()


def test_invalid_condition_inputs_rejected():
    with pytest.raises(ValueError):
        L.make_condition("Indicateur inexistant", ">", "Valeur", 1)
    with pytest.raises(ValueError):
        L.make_condition("Prix", "!=", "Valeur", 1)
    with pytest.raises(ValueError):
        L.make_condition("Prix", ">", "Valeur", None)


def test_projection_view_appends_projected_candles_to_history():
    v = L.projection_view(_df(), "Pétrole")
    assert len(v["payload"]["candles"]) == 90 + 12 and "color" in v["payload"]["candles"][-1]


def test_chart_height_reserves_room_for_rsi():
    assert L.chart_height({"rsi": [1]}) > L.chart_height({})
