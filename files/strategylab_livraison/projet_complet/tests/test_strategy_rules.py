import pandas as pd
import pytest

from indicators.base import IndicatorEngine
from strategy.conditions import evaluate_condition
from strategy.rules import evaluate_rule
from strategy.builder import StrategyBuilder


def _df():
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC"),
        "open": [10, 10, 10, 10, 10],
        "high": [10, 10, 10, 10, 10],
        "low": [10, 10, 10, 10, 10],
        "close": [10, 20, 30, 5, 40],
    })


def test_numeric_threshold_condition():
    engine = IndicatorEngine(_df())
    cond = {"left": {"name": "PRICE"}, "operator": ">", "right": 15}
    out = evaluate_condition(engine, cond)
    assert list(out) == [False, True, True, False, True]


def test_indicator_vs_indicator_condition():
    engine = IndicatorEngine(_df())
    cond = {
        "left": {"name": "PRICE"}, "operator": ">",
        "right": {"name": "SMA", "params": {"window": 2}},
    }
    out = evaluate_condition(engine, cond)
    # SMA(2) est NaN à la 1ère barre -> jamais de signal tant que non défini
    assert out.iloc[0] == False


def test_and_logic_requires_all_conditions():
    engine = IndicatorEngine(_df())
    rule = {
        "logic": "AND",
        "conditions": [
            {"left": {"name": "PRICE"}, "operator": ">", "right": 5},
            {"left": {"name": "PRICE"}, "operator": "<", "right": 25},
        ],
    }
    out = evaluate_rule(engine, rule)
    assert list(out) == [True, True, False, False, False]


def test_or_logic_requires_any_condition():
    engine = IndicatorEngine(_df())
    rule = {
        "logic": "OR",
        "conditions": [
            {"left": {"name": "PRICE"}, "operator": "<", "right": 8},
            {"left": {"name": "PRICE"}, "operator": ">", "right": 35},
        ],
    }
    out = evaluate_rule(engine, rule)
    assert list(out) == [False, False, False, True, True]


def test_empty_rule_conditions_rejected():
    engine = IndicatorEngine(_df())
    with pytest.raises(ValueError, match="au moins une condition"):
        evaluate_rule(engine, {"logic": "AND", "conditions": []})


def test_unknown_operator_rejected():
    engine = IndicatorEngine(_df())
    with pytest.raises(ValueError, match="Opérateur inconnu"):
        evaluate_condition(engine, {"left": {"name": "PRICE"}, "operator": "!=", "right": 5})


def test_strategy_builder_adds_signal_columns():
    buy = {"logic": "AND", "conditions": [{"left": {"name": "PRICE"}, "operator": ">", "right": 100}]}
    sell = {"logic": "AND", "conditions": [{"left": {"name": "PRICE"}, "operator": "<", "right": 0}]}
    out = StrategyBuilder(buy, sell).apply(_df())
    assert "buy_signal" in out.columns and "sell_signal" in out.columns
    assert out["buy_signal"].dtype == bool
