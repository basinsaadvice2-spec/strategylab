import pandas as pd

from indicators.base import IndicatorEngine
from strategy.conditions import evaluate_condition

_LOGIC = {"AND", "OR"}


def evaluate_rule(engine: IndicatorEngine, rule: dict) -> pd.Series:
    """rule = {"logic": "AND" | "OR", "conditions": [condition, ...]}"""
    logic = rule.get("logic", "AND")
    if logic not in _LOGIC:
        raise ValueError(f"logic doit être AND ou OR, reçu: {logic}")

    conditions = rule.get("conditions", [])
    if not conditions:
        raise ValueError("Une règle doit contenir au moins une condition.")

    results = [evaluate_condition(engine, c) for c in conditions]

    combined = results[0]
    for r in results[1:]:
        combined = (combined & r) if logic == "AND" else (combined | r)
    return combined
