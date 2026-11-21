import time
import pandas as pd
import pytest

from data.realtime import RealtimeDataProvider, import_new_bars


def test_realtime_provider_without_fetch_fn_raises_clear_error():
    provider = RealtimeDataProvider()
    with pytest.raises(NotImplementedError, match="live connectée"):
        provider.get_ohlcv("GOLD")


def test_realtime_provider_caches_within_refresh_window():
    calls = {"n": 0}

    def fetch(symbol):
        calls["n"] += 1
        ts = pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC")
        return pd.DataFrame({
            "timestamp": ts, "open": [1] * 5, "high": [2] * 5,
            "low": [0.5] * 5, "close": [1.5] * 5, "volume": [10] * 5,
        })

    provider = RealtimeDataProvider(fetch_fn=fetch, refresh_seconds=10)
    provider.get_ohlcv("GOLD")
    provider.get_ohlcv("GOLD")
    assert calls["n"] == 1  # deuxième appel servi depuis le cache


def test_realtime_provider_refetches_after_expiry():
    calls = {"n": 0}

    def fetch(symbol):
        calls["n"] += 1
        ts = pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC")
        return pd.DataFrame({
            "timestamp": ts, "open": [1] * 5, "high": [2] * 5,
            "low": [0.5] * 5, "close": [1.5] * 5, "volume": [10] * 5,
        })

    provider = RealtimeDataProvider(fetch_fn=fetch, refresh_seconds=1)
    provider.get_ohlcv("GOLD")
    time.sleep(1.1)
    provider.get_ohlcv("GOLD")
    assert calls["n"] == 2


def test_realtime_provider_validates_incoming_data():
    def fetch_bad(symbol):
        ts = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
        return pd.DataFrame({
            "timestamp": ts, "open": [1, -1, 1], "high": [2, 2, 2],
            "low": [0.5, 0.5, 0.5], "close": [1.5, 1.5, 1.5], "volume": [10, 10, 10],
        })

    provider = RealtimeDataProvider(fetch_fn=fetch_bad)
    with pytest.raises(ValueError, match="positifs"):
        provider.get_ohlcv("GOLD")


def test_import_new_bars_skips_duplicates(tmp_path):
    existing = tmp_path / "asset.csv"
    new_bars = tmp_path / "new.csv"
    pd.DataFrame({
        "timestamp": ["2025-01-01", "2025-01-02"], "open": [10, 11],
        "high": [11, 12], "low": [9, 10], "close": [10.5, 11.5], "volume": [100, 100],
    }).to_csv(existing, index=False)
    pd.DataFrame({
        "timestamp": ["2025-01-02", "2025-01-03"], "open": [11, 12],
        "high": [12, 13], "low": [10, 11], "close": [11.5, 12.5], "volume": [100, 100],
    }).to_csv(new_bars, index=False)

    added = import_new_bars(existing, new_bars)
    result = pd.read_csv(existing)
    assert added == 1
    assert len(result) == 3


def test_import_new_bars_creates_file_if_missing(tmp_path):
    existing = tmp_path / "asset.csv"
    new_bars = tmp_path / "new.csv"
    pd.DataFrame({
        "timestamp": ["2025-01-01"], "open": [10], "high": [11],
        "low": [9], "close": [10.5], "volume": [100],
    }).to_csv(new_bars, index=False)

    added = import_new_bars(existing, new_bars)
    assert added == 1
    assert existing.exists()
