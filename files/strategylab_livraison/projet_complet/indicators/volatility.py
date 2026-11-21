import pandas as pd


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range (méthode de Wilder). `df` doit contenir
    high, low, close."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def bollinger_bands(series: pd.Series, window: int = 20, n_std: float = 2.0):
    """Retourne (bande_haute, bande_médiane, bande_basse)."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    middle = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    upper = middle + n_std * std
    lower = middle - n_std * std
    return upper, middle, lower


def bollinger_bandwidth(series: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.Series:
    """Largeur des bandes en % du prix — mesure de compression/expansion
    de la volatilité, utile pour détecter les phases de range serré."""
    upper, middle, lower = bollinger_bands(series, window, n_std)
    return (upper - lower) / middle * 100


def donchian_channel(df: pd.DataFrame, window: int = 20):
    """Retourne (canal_haut, canal_bas): plus haut/plus bas sur `window`
    barres. Base des stratégies de breakout classiques (Turtle Trading)."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    upper = df["high"].rolling(window=window, min_periods=window).max()
    lower = df["low"].rolling(window=window, min_periods=window).min()
    return upper, lower


def keltner_channel(df: pd.DataFrame, ema_window: int = 20, atr_window: int = 10,
                     multiplier: float = 2.0):
    """Retourne (canal_haut, canal_bas) basés sur une EMA +/- un multiple
    de l'ATR (moins sensible aux pics isolés que Bollinger)."""
    from indicators.trend import ema
    middle = ema(df["close"], ema_window)
    band = atr(df, atr_window) * multiplier
    return middle + band, middle - band


def rolling_stddev(series: pd.Series, window: int = 20) -> pd.Series:
    """Écart-type glissant du prix — mesure brute de dispersion."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.rolling(window=window, min_periods=window).std()
