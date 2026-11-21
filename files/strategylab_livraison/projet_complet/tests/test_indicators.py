import pandas as pd
import numpy as np
import pytest

from indicators import trend, momentum, volatility


def test_sma_known_values():
    s = pd.Series([1, 2, 3, 4, 5])
    out = trend.sma(s, window=3)
    assert pd.isna(out.iloc[0]) and pd.isna(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)   # (1+2+3)/3
    assert out.iloc[4] == pytest.approx(4.0)   # (3+4+5)/3


def test_ema_reacts_faster_than_sma_to_recent_move():
    s = pd.Series([10] * 20 + [20] * 5)
    sma20 = trend.sma(s, 20).iloc[-1]
    ema20 = trend.ema(s, 20).iloc[-1]
    assert ema20 > sma20  # l'EMA pondère davantage les valeurs récentes


def test_rsi_strictly_increasing_series_is_100():
    s = pd.Series(range(1, 30))
    out = momentum.rsi(s, window=14)
    assert out.iloc[-1] == pytest.approx(100.0)


def test_rsi_strictly_decreasing_series_is_0():
    s = pd.Series(range(30, 1, -1))
    out = momentum.rsi(s, window=14)
    assert out.iloc[-1] == pytest.approx(0.0)


def test_rsi_warmup_is_nan():
    s = pd.Series(range(1, 10))
    out = momentum.rsi(s, window=14)
    assert out.isna().all()


def test_macd_line_equals_ema_diff():
    s = pd.Series(np.linspace(100, 130, 60))
    line, signal, hist = momentum.macd(s, fast=12, slow=26, signal=9)
    ema_fast = trend.ema(s, 12)
    ema_slow = trend.ema(s, 26)
    pd.testing.assert_series_equal(line, ema_fast - ema_slow, check_names=False)
    pd.testing.assert_series_equal(hist, line - signal, check_names=False)


def test_atr_nonnegative():
    df = pd.DataFrame({
        "high": [10, 11, 10.5, 12, 11.8],
        "low": [9, 9.5, 9.8, 10.5, 10.9],
        "close": [9.5, 10.8, 10.0, 11.5, 11.2],
    })
    out = volatility.atr(df, window=3)
    assert (out.dropna() >= 0).all()


def test_crossover_detects_single_event():
    a = pd.Series([1, 2, 3, 5, 4])
    b = pd.Series([3, 3, 3, 3, 3])
    cross = trend.crossover(a, b)
    assert list(cross) == [False, False, False, True, False]


def test_crossunder_detects_single_event():
    a = pd.Series([5, 4, 3, 1, 2])
    b = pd.Series([3, 3, 3, 3, 3])
    cross = trend.crossunder(a, b)
    assert list(cross) == [False, False, False, True, False]
