import pandas as pd


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume: cumule le volume signé par le sens de la
    clôture. Sert à repérer une divergence entre prix et volume."""
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    direction = df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * df["volume"]).cumsum()


def vwap(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Volume Weighted Average Price glissant sur `window` barres (pas
    le VWAP intrajournalier classique, mais son équivalent multi-période,
    plus utile pour un backtest sur barres journalières)."""
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    if window < 1:
        raise ValueError("window doit être >= 1")
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    return (pv.rolling(window, min_periods=window).sum() /
            df["volume"].rolling(window, min_periods=window).sum())


def mfi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Money Flow Index — un RSI pondéré par le volume, borné [0,100]."""
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    if window < 1:
        raise ValueError("window doit être >= 1")
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    raw_money_flow = typical_price * df["volume"]
    direction = typical_price.diff()

    pos_flow = raw_money_flow.where(direction > 0, 0.0)
    neg_flow = raw_money_flow.where(direction < 0, 0.0)

    pos_sum = pos_flow.rolling(window, min_periods=window).sum()
    neg_sum = neg_flow.rolling(window, min_periods=window).sum()

    money_ratio = pos_sum / neg_sum.replace(0, pd.NA)
    return (100 - (100 / (1 + money_ratio))).astype(float)


def cmf(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Chaikin Money Flow — pression acheteuse/vendeuse pondérée par le
    volume, borné [-1, 1]."""
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    if window < 1:
        raise ValueError("window doit être >= 1")
    range_ = (df["high"] - df["low"]).replace(0, pd.NA)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / range_
    mfv = mfm * df["volume"]
    return (mfv.rolling(window, min_periods=window).sum() /
            df["volume"].rolling(window, min_periods=window).sum())
