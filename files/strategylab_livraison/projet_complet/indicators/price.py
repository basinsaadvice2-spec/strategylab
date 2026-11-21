import pandas as pd


def price(df: pd.DataFrame) -> pd.Series:
    return df["close"]


def pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    if periods < 1:
        raise ValueError("periods doit être >= 1")
    return series.pct_change(periods=periods) * 100


def volume(df: pd.DataFrame) -> pd.Series:
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    return df["volume"]
