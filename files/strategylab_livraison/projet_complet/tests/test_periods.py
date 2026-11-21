import pandas as pd
import pytest

from data.periods import resolve_period, chronological_split


def _df(n=1000):
    return pd.DataFrame({
        "timestamp": pd.date_range("2015-01-01", periods=n, freq="D", tz="UTC"),
        "close": range(n),
    })


def test_resolve_standard_period_years():
    df = _df(365 * 12)
    out = resolve_period(df, "5Y")
    span_days = (out["timestamp"].max() - out["timestamp"].min()).days
    assert 4 * 365 <= span_days <= 5 * 365 + 5


def test_resolve_short_period_days():
    df = _df(365 * 2)
    out = resolve_period(df, "3D")
    assert len(out) <= 4  # 3 jours + éventuellement la borne


def test_custom_period_requires_bounds():
    df = _df(100)
    with pytest.raises(ValueError, match="custom_start"):
        resolve_period(df, "CUSTOM")


def test_custom_period_filters_correctly():
    df = _df(100)
    out = resolve_period(df, "CUSTOM", custom_start="2015-01-05", custom_end="2015-01-10")
    assert out["timestamp"].min() >= pd.Timestamp("2015-01-05", tz="UTC")
    assert out["timestamp"].max() <= pd.Timestamp("2015-01-10", tz="UTC")


def test_unknown_period_rejected():
    df = _df(10)
    with pytest.raises(ValueError, match="Période inconnue"):
        resolve_period(df, "20Y")


def test_period_with_no_data_raises():
    df = _df(5)
    with pytest.raises(ValueError, match="Aucune donnée"):
        resolve_period(df, "CUSTOM", custom_start="2030-01-01", custom_end="2030-02-01")


def test_chronological_split_preserves_order_and_sizes():
    df = _df(1000)
    dev, val, oos = chronological_split(df, dev_fraction=0.6, validation_fraction=0.2)
    assert len(dev) + len(val) + len(oos) == 1000
    assert dev["timestamp"].max() < val["timestamp"].min()
    assert val["timestamp"].max() < oos["timestamp"].min()


def test_chronological_split_rejects_bad_fractions():
    df = _df(100)
    with pytest.raises(ValueError):
        chronological_split(df, dev_fraction=0.7, validation_fraction=0.5)
