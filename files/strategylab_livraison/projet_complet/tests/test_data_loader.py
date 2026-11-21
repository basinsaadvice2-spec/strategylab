import pytest
from data.loader import load_ohlcv


def _write(tmp_path, content):
    p = tmp_path / "market.csv"
    p.write_text(content)
    return p


def test_missing_values_rejected(tmp_path):
    p = _write(tmp_path,
                "timestamp,open,high,low,close,volume\n"
                "2025-01-01,1,2,0.5,1.5,100\n"
                "2025-01-02,,2,0.5,1.5,100\n")
    with pytest.raises(ValueError, match="Valeurs manquantes"):
        load_ohlcv(p)


def test_duplicate_timestamps_deduplicated(tmp_path):
    p = _write(tmp_path,
                "timestamp,open,high,low,close,volume\n"
                "2025-01-01,1,2,0.5,1.5,100\n"
                "2025-01-01,1,2,0.5,1.6,100\n"
                "2025-01-02,1,2,0.5,1.5,100\n")
    df = load_ohlcv(p)
    assert len(df) == 2


def test_unordered_timestamps_sorted(tmp_path):
    p = _write(tmp_path,
                "timestamp,open,high,low,close,volume\n"
                "2025-01-03,1,2,0.5,1.5,100\n"
                "2025-01-01,1,2,0.5,1.5,100\n"
                "2025-01-02,1,2,0.5,1.5,100\n")
    df = load_ohlcv(p)
    assert df["timestamp"].is_monotonic_increasing


def test_incoherent_ohlc_rejected(tmp_path):
    p = _write(tmp_path,
                "timestamp,open,high,low,close,volume\n"
                "2025-01-01,1,1.1,0.9,1.5,100\n")
    with pytest.raises(ValueError, match="incohérentes"):
        load_ohlcv(p)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_ohlcv(tmp_path / "nope.csv")
