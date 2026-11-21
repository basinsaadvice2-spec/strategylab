import pandas as pd
import numpy as np
import pytest

from indicators.base import IndicatorEngine, list_available_indicators
from indicators import volatility, momentum, trend, volume as volume_mod


def _ohlcv(n=120, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.5, 2, n)
    low = close - rng.uniform(0.5, 2, n)
    open_ = close + rng.normal(0, 0.5, n)
    vol = rng.integers(1000, 5000, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
        "open": open_, "high": high, "low": low, "close": close, "volume": vol,
    })


def test_at_least_20_new_indicators_available():
    # 8 indicateurs existaient en V1 (SMA, EMA, RSI, ATR, PRICE, PCT_CHANGE,
    # VOLUME, MACD x3) -> on doit être largement au-dessus de 20 au total.
    names = list_available_indicators()
    assert len(names) >= 28


def test_all_indicators_compute_without_error_on_default_params():
    df = _ohlcv()
    engine = IndicatorEngine(df)
    for ind in list_available_indicators():
        if ind in ("CROSSOVER", "CROSSUNDER", "SMA", "EMA"):
            continue  # nécessitent un paramètre explicite, testés à part
        series = engine.get({"name": ind})
        assert len(series) == len(df)
        assert series.notna().any(), f"{ind} ne produit jamais de valeur"


def test_bollinger_bands_ordering():
    df = _ohlcv()
    upper, middle, lower = volatility.bollinger_bands(df["close"], window=20)
    valid = upper.notna()
    assert (upper[valid] >= middle[valid]).all()
    assert (middle[valid] >= lower[valid]).all()


def test_stochastic_bounded_0_100():
    df = _ohlcv()
    k, d = momentum.stochastic(df)
    assert k.dropna().between(0, 100).all()
    assert d.dropna().between(0, 100).all()


def test_williams_r_bounded_negative_0():
    df = _ohlcv()
    wr = momentum.williams_r(df)
    assert wr.dropna().between(-100, 0).all()


def test_adx_nonnegative():
    df = _ohlcv()
    out = trend.adx(df)
    assert (out.dropna() >= 0).all()


def test_obv_requires_volume_column():
    df = _ohlcv().drop(columns=["volume"])
    with pytest.raises(ValueError, match="volume"):
        volume_mod.obv(df)


def test_mfi_bounded_0_100():
    df = _ohlcv()
    out = volume_mod.mfi(df)
    assert out.dropna().between(0, 100).all()


def test_cmf_bounded_minus1_1():
    df = _ohlcv()
    out = volume_mod.cmf(df)
    assert out.dropna().between(-1, 1).all()


def test_donchian_upper_above_lower():
    df = _ohlcv()
    upper, lower = volatility.donchian_channel(df, window=20)
    valid = upper.notna()
    assert (upper[valid] >= lower[valid]).all()


def test_unknown_indicator_lists_available_ones_in_error():
    engine = IndicatorEngine(_ohlcv())
    with pytest.raises(ValueError, match="ADX"):
        engine.get({"name": "NOT_A_REAL_INDICATOR"})
