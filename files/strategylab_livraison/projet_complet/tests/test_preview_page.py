import json
import re

from ui import preview_page as pp


def _small():
    return {"OIL": {"label": "Pétrole (démo)", "df": pp.demo_dataset(65, 0.017, 21, with_volume=False, n=900)}}


def test_every_asset_period_strategy_combination_is_precomputed():
    data = pp.compute_all(_small())
    for pk in pp.PERIODS:
        strategies = data["assets"]["OIL"]["periods"][pk]["strategies"]
        assert set(strategies) == set(pp.STRATEGIES)
        for s in strategies.values():
            assert {"markers", "trades", "report"} <= set(s)


def test_chart_base_is_shared_and_aligned_across_strategies():
    base = pp.compute_all(_small())["assets"]["OIL"]["periods"]["1Y"]["base"]
    assert len(base["candles"]) == len(base["rsi"]) and base["volume"] == []   # pétrole démo : pas de volume


def test_volume_strategy_never_trades_on_asset_without_volume():
    s = pp.compute_all(_small())["assets"]["OIL"]["periods"]["3Y"]["strategies"]["boll_mfi"]
    assert s["report"]["n_trades"] == 0 and s["markers"] == []


def test_projection_included_with_four_checkpoints():
    proj = pp.compute_all(_small())["assets"]["OIL"]["projection"]
    assert len(proj["table"]) == 4 and len(proj["payload"]["candles"]) == 102


def test_html_is_one_page_with_balanced_scripts_attribution_and_demo_label():
    html = pp.build_preview_html(_small())
    assert len(re.findall(r"<script", html)) == len(re.findall(r"</script>", html))
    assert "lightweight-charts@4.2.0" in html and "https://www.tradingview.com/" in html
    assert "DÉMO — données simulées" in html


def test_data_blob_is_valid_json_after_replacing_js_infinity():
    html = pp.build_preview_html(_small())
    blob = html.split("const D = ")[1].split(", T = D.theme")[0]
    json.loads(blob.replace("Infinity", "null"))
