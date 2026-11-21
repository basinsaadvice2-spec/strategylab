"""
Une condition compare un indicateur à un seuil numérique OU à un autre
indicateur (ex: "prix > SMA 200"). Pas de code à écrire côté client — tout
est déclaratif (dict), ce qui permet de construire l'écran "Strategy
Builder" sans exposer Python à l'utilisateur final.
"""
import operator as _op
import pandas as pd

from indicators.base import IndicatorEngine

_OPERATORS = {
    ">": _op.gt,
    "<": _op.lt,
    ">=": _op.ge,
    "<=": _op.le,
    "=": _op.eq,
}


def evaluate_condition(engine: IndicatorEngine, condition: dict) -> pd.Series:
    op_symbol = condition["operator"]
    if op_symbol not in _OPERATORS:
        raise ValueError(
            f"Opérateur inconnu: {op_symbol}. Disponibles: {list(_OPERATORS)}"
        )

    left = engine.get(condition["left"])

    right = condition["right"]
    if isinstance(right, dict):
        right = engine.get(right)
    elif not isinstance(right, (int, float)):
        raise ValueError(
            "`right` doit être un nombre ou une spec d'indicateur (dict)."
        )

    result = _OPERATORS[op_symbol](left, right)
    # Toute ligne où l'indicateur n'est pas encore défini (préchauffage,
    # ex. RSI avant `window` barres) ne doit jamais déclencher un signal.
    result = result.fillna(False)
    return result
