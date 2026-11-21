import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    if span < 1:
        raise ValueError("span doit être >= 1")
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """True sur la barre où `a` vient de croiser `b` par le haut (a était
    <= b la barre précédente, a > b maintenant). N'utilise que des données
    déjà connues à la barre courante — aucun look-ahead.
    """
    prev_a, prev_b = a.shift(1), b.shift(1)
    return (prev_a <= prev_b) & (a > b)


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    """True sur la barre où `a` vient de croiser `b` par le bas."""
    prev_a, prev_b = a.shift(1), b.shift(1)
    return (prev_a >= prev_b) & (a < b)


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average Directional Index (Wilder) — force de la tendance,
    indépendamment de sa direction (0 = pas de tendance, >25 = tendance
    marquée). L'un des indicateurs les plus utilisés pour filtrer les
    stratégies de suivi de tendance."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    high, low, close = df["high"], df["low"], df["close"]
    prev_high, prev_low, prev_close = high.shift(1), low.shift(1), close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move.clip(lower=0)

    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    alpha = 1 / window
    atr_ = tr.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean() / atr_

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=window).mean().astype(float)


def aroon(df: pd.DataFrame, window: int = 25):
    """Retourne (aroon_up, aroon_down) — mesure depuis combien de temps
    le plus haut/plus bas de la fenêtre a été atteint (100 = atteint à
    l'instant, 0 = atteint il y a `window` barres)."""
    if window < 1:
        raise ValueError("window doit être >= 1")

    def periods_since_extreme(s, agg):
        return s.rolling(window + 1, min_periods=window + 1).apply(
            lambda x: window - (x.argmax() if agg == "max" else x.argmin()), raw=True
        )

    up = 100 * (window - periods_since_extreme(df["high"], "max")) / window
    down = 100 * (window - periods_since_extreme(df["low"], "min")) / window
    return up.astype(float), down.astype(float)
