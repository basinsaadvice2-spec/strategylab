import pandas as pd
import pytest

from metrics.report import build_report


def _trades(pnls):
    return pd.DataFrame([
        {"pnl_dollars": p, "fees": 1.0, "duration_bars": 3, "sltp_ambiguous": False}
        for p in pnls
    ])


def test_return_and_drawdown():
    equity = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=3, freq="D"),
        "equity": [1000.0, 1200.0, 900.0],
    })
    report = build_report(_trades([]), equity, initial_cash=1000.0, asset="GOLD",
                           period_label="1 an", commission_rate=0.001, slippage_rate=0.0005)
    assert report["return_pct"] == pytest.approx(-10.0)
    assert report["max_drawdown_pct"] == pytest.approx((900 / 1200 - 1) * 100)


def test_win_rate_and_profit_factor():
    trades = _trades([100, -50, 100, -50, -50])
    equity = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=2, freq="D"),
        "equity": [1000.0, 1050.0],
    })
    report = build_report(trades, equity, initial_cash=1000.0, asset="OIL",
                           period_label="1 an", commission_rate=0.001, slippage_rate=0.0005)
    assert report["n_trades"] == 5
    assert report["win_rate_pct"] == pytest.approx(40.0)
    assert report["profit_factor"] == pytest.approx(200 / 150)


def test_reliable_sample_flag():
    few_trades = _trades([10] * 5)
    equity = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=2, freq="D"),
                            "equity": [1000.0, 1010.0]})
    report = build_report(few_trades, equity, initial_cash=1000.0, asset="GOLD",
                           period_label="1 an", commission_rate=0.001, slippage_rate=0.0005)
    assert report["reliable_sample"] is False


def test_zero_initial_cash_rejected():
    with pytest.raises(ValueError):
        build_report(_trades([]), pd.DataFrame(), initial_cash=0, asset="GOLD",
                      period_label="1 an", commission_rate=0.001, slippage_rate=0.0005)


def test_never_claims_future_profitability():
    equity = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=2, freq="D"),
                            "equity": [1000.0, 1010.0]})
    report = build_report(_trades([]), equity, initial_cash=1000.0, asset="GOLD",
                           period_label="1 an", commission_rate=0.001, slippage_rate=0.0005)
    assert "garantie" in report["disclaimer"].lower()
