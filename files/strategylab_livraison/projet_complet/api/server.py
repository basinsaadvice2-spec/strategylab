"""
API HTTP de StrategyLab — bibliothèque standard uniquement (pas de framework à installer).
Toute l'analyse est faite ici, en Python ; le navigateur n'affiche que le résultat.

  GET  /api/config      périodes, indicateurs, opérateurs, valeurs par défaut
  GET  /api/markets     disponibilité et fraîcheur des données de chaque actif
  POST /api/backtest    lance un backtest (corps JSON, pourcentages en unités : 2 = 2 %)
  POST /api/projection  projection statistique (plage de probabilité)
  GET  /healthz         sonde de santé
  GET  /                la page web (web/index.html), si présente

Variables d'environnement : PORT (8080), ALLOWED_ORIGINS (séparés par ; , ou espace ; "*" par
défaut), TWELVEDATA_API_KEY (or). Aucune clé n'est jamais écrite dans le code ni dans les logs.
"""
import gzip
import json
import logging
import math
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from config.settings import (DEFAULT_COMMISSION_RATE, DEFAULT_INITIAL_CASH, DEFAULT_RISK_PCT,
                             DEFAULT_SLIPPAGE_RATE, DEFAULT_STOP_LOSS_PCT, DEFAULT_TAKE_PROFIT_PCT,
                             STANDARD_PERIODS)
from data.live_providers import DataUnavailable, LiveDataProvider
from ui import app_logic as L

logger = logging.getLogger("strategylab.api")

MAX_BODY_BYTES = 20_000
MAX_CONDITIONS = 5
MAX_CONCURRENT_JOBS = 4
ASSET_LABELS = {"OIL": "Pétrole (WTI)", "GOLD": "Or (XAU/USD)"}
INDEX_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEFAULT_RULES = {
    "buy": {"logic": "AND", "conditions": [
        {"left": "RSI (14)", "operator": "<", "mode": "Valeur", "value": 30},
        {"left": "Prix", "operator": ">", "mode": "Indicateur", "right": "SMA 200"}]},
    "sell": {"logic": "AND", "conditions": [
        {"left": "RSI (14)", "operator": ">", "mode": "Valeur", "value": 70},
        {"left": "Prix", "operator": "<", "mode": "Indicateur", "right": "SMA 200"}]},
}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ------------------------------------------------------------------ validation

def _number(body: dict, key: str, lo: float, hi: float, default=None) -> float:
    value = body.get(key, default)
    if value is None:
        raise ApiError(400, f"Champ manquant : {key}.")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ApiError(400, f"{key} doit être un nombre.")
    if not lo <= value <= hi:
        raise ApiError(400, f"{key} doit être compris entre {lo} et {hi}.")
    return float(value)


def _asset(body: dict) -> str:
    asset = body.get("asset")
    if asset not in ASSET_LABELS:
        raise ApiError(400, f"Actif inconnu : choisis parmi {', '.join(ASSET_LABELS)}.")
    return asset


def _rule(raw, name: str) -> dict:
    if not isinstance(raw, dict) or raw.get("logic") not in ("AND", "OR"):
        raise ApiError(400, f"Règle {name} invalide (logic doit être AND ou OR).")
    conditions = raw.get("conditions")
    if not isinstance(conditions, list) or not 1 <= len(conditions) <= MAX_CONDITIONS:
        raise ApiError(400, f"Règle {name} : entre 1 et {MAX_CONDITIONS} conditions.")
    parsed = []
    for c in conditions:
        if not isinstance(c, dict):
            raise ApiError(400, f"Règle {name} : condition invalide.")
        value = c.get("value")
        if c.get("mode") == "Valeur" and (isinstance(value, bool) or not isinstance(value, (int, float))
                                          or not math.isfinite(value)):
            raise ApiError(400, f"Règle {name} : le seuil doit être un nombre.")
        try:
            parsed.append(L.make_condition(c.get("left"), c.get("operator"), c.get("mode"),
                                           value=value, right_label=c.get("right")))
        except ValueError as exc:
            raise ApiError(400, f"Règle {name} : {exc}") from None
    return L.make_rule(raw["logic"], parsed)


def _clean(obj):
    """JSON strict : numpy -> Python, inf/NaN -> null."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


# ------------------------------------------------------------------ logique des routes

class App:
    def __init__(self, provider: LiveDataProvider):
        self.provider = provider
        self.jobs = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)

    def config(self) -> dict:
        return {
            "periods": [{"key": k, "label": v["label"]} for k, v in STANDARD_PERIODS.items()],
            "indicators": list(L.INDICATOR_CHOICES), "operators": L.OPERATORS,
            "assets": [{"key": k, "label": v} for k, v in ASSET_LABELS.items()],
            "defaults": {"cash": DEFAULT_INITIAL_CASH, "risk_pct": DEFAULT_RISK_PCT * 100,
                         "stop_loss_pct": DEFAULT_STOP_LOSS_PCT * 100, "take_profit_pct": DEFAULT_TAKE_PROFIT_PCT * 100,
                         "commission_pct": DEFAULT_COMMISSION_RATE * 100, "slippage_pct": DEFAULT_SLIPPAGE_RATE * 100,
                         "rules": DEFAULT_RULES},
        }

    def markets(self) -> dict:
        out = []
        for key, label in ASSET_LABELS.items():
            entry = {"key": key, "label": label}
            try:
                df = self.provider.get_ohlcv(key)
                last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
                entry.update(available=True, last_close=round(last, 4), change_pct=round((last / prev - 1) * 100, 2),
                             **{k: v for k, v in self.provider.info(key).items() if k != "fetched_at"})
            except DataUnavailable as exc:
                entry.update(available=False, reason=str(exc))
            out.append(entry)
        return {"markets": out}

    def _load(self, asset: str) -> pd.DataFrame:
        try:
            return self.provider.get_ohlcv(asset)
        except DataUnavailable as exc:
            raise ApiError(503, str(exc)) from None

    def backtest(self, body: dict) -> dict:
        asset = _asset(body)
        period = body.get("period")
        if period not in STANDARD_PERIODS:
            raise ApiError(400, "Période inconnue.")
        custom_start = custom_end = None
        if period == "CUSTOM":
            custom_start, custom_end = body.get("custom_start"), body.get("custom_end")
            if not (isinstance(custom_start, str) and isinstance(custom_end, str)
                    and _DATE.match(custom_start) and _DATE.match(custom_end)):
                raise ApiError(400, "Période personnalisée : dates au format AAAA-MM-JJ.")
        cash = _number(body, "cash", 100, 1e9)
        risk = _number(body, "risk_pct", 0.01, 100) / 100
        stop = _number(body, "stop_loss_pct", 0.05, 99) / 100
        take = _number(body, "take_profit_pct", 0.05, 500) / 100
        commission = _number(body, "commission_pct", 0, 5) / 100
        slippage = _number(body, "slippage_pct", 0, 5) / 100
        buy, sell = _rule(body.get("buy"), "d'achat"), _rule(body.get("sell"), "de vente")

        full_df = self._load(asset)
        if not self.jobs.acquire(timeout=3):
            raise ApiError(503, "Serveur occupé, réessaie dans quelques secondes.")
        try:
            try:
                res = L.run_analysis(full_df, period, buy, sell, cash, risk, stop, take, commission, slippage,
                                     ASSET_LABELS[asset], custom_start, custom_end)
            except ValueError as exc:
                raise ApiError(400, str(exc)) from None
        finally:
            self.jobs.release()
        return _clean(self._format_backtest(res, asset, stop, slippage))

    def _format_backtest(self, res: dict, asset: str, stop: float, slippage: float) -> dict:
        rep, extra = res["report"], L.summarize(res, stop, slippage)
        fields = ("return_pct", "final_equity", "initial_cash", "max_drawdown_pct", "n_trades", "n_wins", "n_losses",
                  "win_rate_pct", "avg_win_dollars", "avg_loss_dollars", "profit_factor", "expectancy_dollars",
                  "total_fees_dollars", "avg_trade_duration_bars", "reliable_sample", "period", "disclaimer")
        report = {k: rep[k] for k in fields}
        report["profit_factor_infinite"] = rep["profit_factor"] == float("inf")
        report.update(sharpe_ratio=extra["sharpe_ratio"], slippage_estimated_dollars=extra["slippage_estimated_dollars"])
        eq = [{"time": pd.Timestamp(r.timestamp).strftime("%Y-%m-%d"), "value": round(float(r.equity), 2)}
              for r in res["equity"].itertuples()]
        return {"asset": asset, "report": report, "trades": extra["trade_rows"], "equity": eq,
                "exit_reasons": extra["exit_reasons"], "chart": res["chart_payload"], "data": self._data_info(asset)}

    def _data_info(self, asset: str) -> dict:
        info = self.provider.info(asset)
        return {k: info.get(k) for k in ("source", "last_date", "n_bars", "has_volume", "ohlc_approx", "stale_error")}

    def projection(self, body: dict) -> dict:
        asset = _asset(body)
        full_df = self._load(asset)
        try:
            view = L.projection_view(full_df, ASSET_LABELS[asset])
        except ValueError as exc:
            raise ApiError(400, str(exc)) from None
        return _clean({"asset": asset, **view, "data": self._data_info(asset)})


# ------------------------------------------------------------------ HTTP

def _allowed_origins() -> list:
    raw = os.environ.get("ALLOWED_ORIGINS", "*")
    return [o for o in re.split(r"[;,\s]+", raw) if o] or ["*"]


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        timeout = 30               # coupe les connexions qui traînent
        server_version = "StrategyLab"
        sys_version = ""

        def log_message(self, fmt, *args):      # jamais de corps de requête dans les logs
            logger.info("%s %s", self.address_string(), fmt % args)

        # -- utilitaires
        def _cors(self):
            origin, allowed = self.headers.get("Origin"), _allowed_origins()
            if "*" in allowed:
                self.send_header("Access-Control-Allow-Origin", "*")
            elif origin in allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
            if len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", ""):
                body = gzip.compress(body, 5)
                self.send_response(status)
                self.send_header("Content-Encoding", "gzip")
            else:
                self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

        def _handle(self, fn):
            try:
                self._json(200, fn())
            except ApiError as exc:
                self._json(exc.status, {"error": exc.message})
            except Exception:                               # jamais de trace d'erreur côté client
                logger.exception("Erreur interne")
                self._json(500, {"error": "Erreur interne du serveur."})

        # -- méthodes
        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self._cors()
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/healthz":
                return self._json(200, {"ok": True})
            if path == "/api/config":
                return self._handle(app.config)
            if path == "/api/markets":
                return self._handle(app.markets)
            if path in ("/", "/index.html") and INDEX_PATH.exists():
                return self._send(200, INDEX_PATH.read_bytes(), "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
            self._json(404, {"error": "Introuvable."})

        def do_POST(self):
            path = urlparse(self.path).path
            routes = {"/api/backtest": app.backtest, "/api/projection": app.projection}
            if path not in routes:
                return self._json(404, {"error": "Introuvable."})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._json(411, {"error": "Content-Length requis."})
            if length > MAX_BODY_BYTES:
                return self._json(413, {"error": "Requête trop volumineuse."})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._json(400, {"error": "Corps JSON invalide."})
            if not isinstance(body, dict):
                return self._json(400, {"error": "Le corps doit être un objet JSON."})
            self._handle(lambda: routes[path](body))

    return Handler


def create_server(address=("0.0.0.0", 8080), provider: LiveDataProvider | None = None) -> ThreadingHTTPServer:
    provider = provider or LiveDataProvider(twelvedata_api_key=os.environ.get("TWELVEDATA_API_KEY"), ttl_seconds=3600)
    server = ThreadingHTTPServer(address, make_handler(App(provider)))
    server.daemon_threads = True
    return server


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = int(os.environ.get("PORT", "8080"))
    logger.info("StrategyLab API sur le port %d", port)
    create_server(("0.0.0.0", port)).serve_forever()


if __name__ == "__main__":
    main()
