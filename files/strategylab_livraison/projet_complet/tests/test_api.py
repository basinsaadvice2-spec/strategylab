import gzip
import json
import os
import threading
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

import api.server as srv
from api.server import DEFAULT_RULES, create_server
from data.live_providers import LiveDataProvider
from ui import app_logic as L


def _fred_csv(n=2300):
    rng = np.random.default_rng(5)
    dates = pd.bdate_range("2017-01-02", periods=n)
    close = 60 * np.exp(np.cumsum(rng.normal(0, 0.017, n)))
    rows = ["observation_date,DCOILWTICO"] + [f"{d.date()},{c:.2f}" for d, c in zip(dates, close)]
    rows[5] = f"{dates[4].date()},."
    return "\n".join(rows).encode()


def _start():
    csv = _fred_csv()
    server = create_server(("127.0.0.1", 0), LiveDataProvider(http_get=lambda url: csv))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _call(base, path, body=None, headers=None, method=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, hdrs, payload = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, hdrs, payload = e.code, e.headers, e.read()
    if hdrs.get("Content-Encoding") == "gzip":
        payload = gzip.decompress(payload)
    return status, hdrs, payload


def _body(**over):
    base = {"asset": "OIL", "period": "3Y", "cash": 10000, "risk_pct": 2, "stop_loss_pct": 3,
            "take_profit_pct": 6, "commission_pct": 0.1, "slippage_pct": 0.05,
            "buy": {"logic": "AND", "conditions": [{"left": "RSI (14)", "operator": "<", "mode": "Valeur", "value": 40}]},
            "sell": {"logic": "OR", "conditions": [{"left": "RSI (14)", "operator": ">", "mode": "Valeur", "value": 60}]}}
    base.update(over)
    return base


def test_config_lists_periods_indicators_defaults_and_example_rules():
    server, base = _start()
    try:
        status, _, payload = _call(base, "/api/config")
        cfg = json.loads(payload)
        assert status == 200 and "SMA 200" in cfg["indicators"] and cfg["defaults"]["rules"] == DEFAULT_RULES
        assert {"1Y", "3D", "CUSTOM"} <= {p["key"] for p in cfg["periods"]}
    finally:
        server.shutdown()


def test_markets_reports_oil_available_and_gold_missing_key():
    server, base = _start()
    try:
        m = {x["key"]: x for x in json.loads(_call(base, "/api/markets")[2])["markets"]}
        assert m["OIL"]["available"] is True and m["OIL"]["ohlc_approx"] is True
        assert m["OIL"]["last_close"] > 0 and isinstance(m["OIL"]["change_pct"], float)
        assert m["GOLD"]["available"] is False and "TWELVEDATA_API_KEY" in m["GOLD"]["reason"]
    finally:
        server.shutdown()


def test_backtest_returns_complete_strict_json():
    server, base = _start()
    try:
        status, _, payload = _call(base, "/api/backtest", _body())
        out = json.loads(payload)      # JSON strict : pas de NaN / Infinity
        assert status == 200
        assert len(out["chart"]["candles"]) == len(out["chart"]["rsi"]) == len(out["equity"])
        assert out["report"]["n_trades"] == len(out["trades"]) and len(out["chart"]["markers"]) == 2 * len(out["trades"])
        assert {"entry", "exit", "pnl", "reason", "r"} <= set(out["trades"][0])
        assert sum(out["exit_reasons"].values()) == len(out["trades"])
        assert out["data"]["ohlc_approx"] is True and out["data"]["has_volume"] is False
    finally:
        server.shutdown()


def test_bad_inputs_are_rejected_with_400():
    server, base = _start()
    try:
        bad_bodies = [
            _body(asset="SILVER"), _body(period="20Y"), _body(cash=-5), _body(risk_pct=500), _body(stop_loss_pct=0),
            _body(cash="beaucoup"), _body(buy={"logic": "XOR", "conditions": []}),
            _body(buy={"logic": "AND", "conditions": [{"left": "RSI (14)", "operator": "<", "mode": "Valeur", "value": 1}] * 6}),
            _body(buy={"logic": "AND", "conditions": [{"left": "Inexistant", "operator": "<", "mode": "Valeur", "value": 1}]}),
            _body(buy={"logic": "AND", "conditions": [{"left": "RSI (14)", "operator": "<", "mode": "Valeur", "value": "30"}]}),
            _body(period="CUSTOM", custom_start="2020-13-45x", custom_end="2021-01-01"),
        ]
        for b in bad_bodies:
            status, _, payload = _call(base, "/api/backtest", b)
            assert status == 400 and "error" in json.loads(payload), b
        assert _call(base, "/api/backtest", raw=b"{pas du json")[0] == 400
        assert _call(base, "/api/backtest", raw=b"[1, 2]")[0] == 400
    finally:
        server.shutdown()


def test_gold_without_key_gives_503_with_clear_message():
    server, base = _start()
    try:
        status, _, payload = _call(base, "/api/backtest", _body(asset="GOLD"))
        assert status == 503 and "TWELVEDATA_API_KEY" in json.loads(payload)["error"]
    finally:
        server.shutdown()


def test_oversize_body_and_unknown_path():
    server, base = _start()
    try:
        assert _call(base, "/api/backtest", raw=b"x" * 30_000)[0] == 413
        assert _call(base, "/api/nimporte")[0] == 404
        assert _call(base, "/api/nimporte", body={})[0] == 404
    finally:
        server.shutdown()


def test_internal_errors_never_leak_details():
    server, base = _start()
    original = L.run_analysis
    L.run_analysis = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DETAIL-SECRET-/chemin/interne"))
    try:
        status, _, payload = _call(base, "/api/backtest", _body())
        assert status == 500 and b"DETAIL-SECRET" not in payload and b"Traceback" not in payload
    finally:
        L.run_analysis = original
        server.shutdown()


def test_cors_allowlist_and_preflight():
    server, base = _start()
    previous = os.environ.get("ALLOWED_ORIGINS")
    try:
        os.environ["ALLOWED_ORIGINS"] = "https://mon-site.netlify.app;https://autre.example"
        ok = _call(base, "/api/config", headers={"Origin": "https://mon-site.netlify.app"})[1]
        bad = _call(base, "/api/config", headers={"Origin": "https://pirate.example"})[1]
        assert ok.get("Access-Control-Allow-Origin") == "https://mon-site.netlify.app"
        assert bad.get("Access-Control-Allow-Origin") is None
        status, hdrs, _ = _call(base, "/api/backtest", method="OPTIONS", headers={"Origin": "https://mon-site.netlify.app"})
        assert status == 204 and "POST" in hdrs["Access-Control-Allow-Methods"]
        os.environ["ALLOWED_ORIGINS"] = "*"
        assert _call(base, "/api/config", headers={"Origin": "https://x.example"})[1].get("Access-Control-Allow-Origin") == "*"
    finally:
        if previous is None:
            os.environ.pop("ALLOWED_ORIGINS", None)
        else:
            os.environ["ALLOWED_ORIGINS"] = previous
        server.shutdown()


def test_large_responses_are_gzipped_when_accepted():
    server, base = _start()
    try:
        raw_status, raw_hdrs, _ = _call(base, "/api/backtest", _body())
        status, hdrs, payload = _call(base, "/api/backtest", _body(), headers={"Accept-Encoding": "gzip"})
        assert status == 200 and hdrs.get("Content-Encoding") == "gzip" and raw_hdrs.get("Content-Encoding") is None
        assert json.loads(payload)["asset"] == "OIL"
    finally:
        server.shutdown()


def test_projection_endpoint():
    server, base = _start()
    try:
        out = json.loads(_call(base, "/api/projection", {"asset": "OIL"})[2])
        assert len(out["table"]) == 4 and len(out["payload"]["candles"]) == 102
        assert _call(base, "/api/projection", {"asset": "X"})[0] == 400
    finally:
        server.shutdown()


def test_index_is_served_with_security_headers(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<html>ok</html>", encoding="utf-8")
    server, base = _start()
    original = srv.INDEX_PATH
    srv.INDEX_PATH = page
    try:
        status, hdrs, payload = _call(base, "/")
        assert status == 200 and payload == b"<html>ok</html>" and hdrs["X-Content-Type-Options"] == "nosniff"
        assert hdrs["X-Frame-Options"] == "DENY" and hdrs["Referrer-Policy"] == "no-referrer"
    finally:
        srv.INDEX_PATH = original
        server.shutdown()
