import pandas as pd


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """RSI de Wilder. Renvoie NaN pendant la période de préchauffage
    (les `window` premières valeurs), jamais une estimation trompeuse."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    import numpy as np
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(~(avg_gain.isna() | avg_loss.isna()), np.nan)
    return out.astype(float)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Retourne (macd_line, signal_line, histogram)."""
    if fast >= slow:
        raise ValueError("fast doit être < slow")
    ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic(df: pd.DataFrame, k_window: int = 14, d_window: int = 3):
    """Retourne (%K, %D). Oscillateur borné [0,100], classique pour
    repérer surachat/survente à court terme."""
    if k_window < 1 or d_window < 1:
        raise ValueError("les fenêtres doivent être >= 1")
    low_min = df["low"].rolling(window=k_window, min_periods=k_window).min()
    high_max = df["high"].rolling(window=k_window, min_periods=k_window).max()
    denom = (high_max - low_min).replace(0, pd.NA)
    percent_k = 100 * (df["close"] - low_min) / denom
    percent_d = percent_k.rolling(window=d_window, min_periods=d_window).mean()
    return percent_k.astype(float), percent_d.astype(float)


def williams_r(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Williams %R — inverse du Stochastique, borné [-100, 0]."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    high_max = df["high"].rolling(window=window, min_periods=window).max()
    low_min = df["low"].rolling(window=window, min_periods=window).min()
    denom = (high_max - low_min).replace(0, pd.NA)
    return (-100 * (high_max - df["close"]) / denom).astype(float)


def cci(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Commodity Channel Index. Mesure l'écart du prix typique à sa
    moyenne mobile, normalisé par la déviation moyenne."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = typical_price.rolling(window=window, min_periods=window).mean()
    import numpy as np
    mean_dev = typical_price.rolling(window=window, min_periods=window).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    denom = (0.015 * mean_dev).replace(0, pd.NA)
    return ((typical_price - sma_tp) / denom).astype(float)


def roc(series: pd.Series, window: int = 12) -> pd.Series:
    """Rate of Change — variation en % sur `window` périodes (équivalent
    standard de PCT_CHANGE, nommé différemment car très utilisé sous ce
    nom précis en analyse technique)."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.pct_change(periods=window) * 100


def momentum(series: pd.Series, window: int = 10) -> pd.Series:
    """Momentum brut: différence de prix (pas en %) sur `window`
    périodes."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.diff(periods=window)


def trix(series: pd.Series, window: int = 15) -> pd.Series:
    """TRIX: taux de variation d'une triple EMA — filtre le bruit mieux
    qu'un MACD classique, utile sur des tendances de fond."""
    if window < 1:
        raise ValueError("window doit être >= 1")
    ema1 = series.ewm(span=window, adjust=False, min_periods=window).mean()
    ema2 = ema1.ewm(span=window, adjust=False, min_periods=window).mean()
    ema3 = ema2.ewm(span=window, adjust=False, min_periods=window).mean()
    return ema3.pct_change() * 100


def ultimate_oscillator(df: pd.DataFrame, w1: int = 7, w2: int = 14, w3: int = 28) -> pd.Series:
    """Ultimate Oscillator: combine 3 horizons pour réduire les faux
    signaux d'un oscillateur à fenêtre unique."""
    prev_close = df["close"].shift(1)
    bp = df["close"] - pd.concat([df["low"], prev_close], axis=1).min(axis=1)
    tr = pd.concat([df["high"], prev_close], axis=1).max(axis=1) - \
         pd.concat([df["low"], prev_close], axis=1).min(axis=1)

    def avg(w):
        return bp.rolling(w, min_periods=w).sum() / tr.rolling(w, min_periods=w).sum()

    a1, a2, a3 = avg(w1), avg(w2), avg(w3)
    return 100 * (4 * a1 + 2 * a2 + a3) / 7
