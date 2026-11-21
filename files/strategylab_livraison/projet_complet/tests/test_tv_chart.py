import numpy as np
import pandas as pd

from ui import tv_chart


def _df(n=40):
    ts = pd.bdate_range("2025-01-01", periods=n, tz="UTC")
    c = 100 + np.arange(n, dtype=float)
    return pd.DataFrame({"timestamp": ts, "open": c, "high": c + 1, "low": c - 1, "close": c,
                         "volume": 0.0, "RSI14": [np.nan] * 14 + list(np.linspace(30, 70, n - 14))})


def test_candles_use_iso_day_and_rounded_numbers():
    c = tv_chart.df_to_candles(_df())
    assert c[0] == {"time": "2025-01-01", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}


def test_line_keeps_one_point_per_bar_with_empty_warmup_points():
    line = tv_chart.series_to_line(_df(), "RSI14")
    assert len(line) == 40 and line[0] == {"time": "2025-01-01"} and "value" in line[20]


def test_volume_is_empty_when_asset_has_no_real_volume():
    assert tv_chart.df_to_volume(_df()) == []
    df = _df(); df["volume"] = 1000.0
    assert len(tv_chart.df_to_volume(df)) == 40


def test_markers_are_sorted_and_have_expected_shapes():
    ts = pd.bdate_range("2025-01-01", periods=40, tz="UTC")
    trades = pd.DataFrame([
        {"entry_time": ts[20], "exit_time": ts[25], "pnl_dollars": -10.0, "exit_reason": "SL"},
        {"entry_time": ts[3], "exit_time": ts[9], "pnl_dollars": 55.0, "exit_reason": "TP"},
    ])
    m = tv_chart.trades_to_markers(trades)
    assert [x["time"] for x in m] == sorted(x["time"] for x in m)
    assert {x["shape"] for x in m} == {"arrowUp", "arrowDown"}
    assert any("Objectif +55$" == x["text"] for x in m) and any("Stop −10$" == x["text"] for x in m)


def test_html_pins_library_version_and_shows_tradingview_attribution():
    html = tv_chart.build_chart_html({"title": "t", "candles": tv_chart.df_to_candles(_df())})
    assert "lightweight-charts@4.2.0" in html and "https://www.tradingview.com/" in html


def test_html_payload_cannot_break_out_of_the_script_tag():
    html = tv_chart.build_chart_html({"title": "</script><img src=x onerror=alert(1)>", "candles": []})
    assert "<img src=x" not in html


def test_projection_candles_are_visually_distinct():
    c = tv_chart.projection_candles([{"time": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5}])
    assert c[0]["color"].startswith("rgba") and "borderColor" in c[0]
