"""
Données de marché RÉELLES, interrogées côté serveur (Python) — aucune donnée
simulée, aucune clé dans le code.

- PÉTROLE (WTI) : EIA via FRED, gratuit, sans clé. La source ne publie qu'UNE
  clôture par jour : on reconstruit des barres (open = clôture précédente,
  high/low = bornes open/close, volume = 0). Les indicateurs de volume sont
  neutralisés par le moteur dans ce cas (voir indicators/base.py).
- OR (XAU/USD) : Twelve Data (offre gratuite), clé API requise, lue dans
  l'environnement / les secrets de l'hébergeur — jamais écrite dans le code.

LiveDataProvider garde un cache mémoire (TTL, 1 h par défaut) : plusieurs
utilisateurs de l'app partagent la même récupération. Si la source tombe, on
sert la dernière copie connue en le SIGNALANT (jamais de faux silence).
"""
import io
import json
import logging
import threading
import time
import urllib.parse
import urllib.request

import pandas as pd

from data.provider import DataProvider
from data.loader import validate_ohlcv

logger = logging.getLogger(__name__)

FRED_WTI_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILWTICO"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"   # API officielle (clé gratuite)
TWELVEDATA_URL = "https://api.twelvedata.com/time_series"
FIRESTORE_URL = "https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents"
FIREBASE_MAX_STALE_DAYS = 7     # au-delà, les données Firebase sont jugées périmées et la lecture directe prend le relais


class DataUnavailable(RuntimeError):
    """Source indisponible (réseau, clé manquante, réponse inattendue)."""


def _http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "StrategyLab/1.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _redact(message: str, *secrets) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    return message


# ---------- Analyse des réponses (fonctions pures, testables hors réseau) ----------

def parse_fred_wti(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text))
    if df.shape[1] < 2:
        raise DataUnavailable("FRED : format de réponse inattendu.")
    df = df.iloc[:, :2].copy()
    df.columns = ["timestamp", "close"]
    return _closes_to_bars(df)


def parse_fred_api(payload: dict) -> pd.DataFrame:
    """Réponse JSON de l'API officielle FRED (series/observations)."""
    obs = payload.get("observations")
    if not isinstance(obs, list):
        raise DataUnavailable(f"FRED (API) : {payload.get('error_message', 'réponse inattendue')}")
    return _closes_to_bars(pd.DataFrame({"timestamp": [o.get("date") for o in obs],
                                         "close": [o.get("value") for o in obs]}))


def _fs_value(v: dict):
    """Valeur typée de l'API REST Firestore -> valeur Python (les entiers arrivent sous forme de texte)."""
    if "stringValue" in v:
        return v["stringValue"]
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "integerValue" in v:
        return float(v["integerValue"])
    if "booleanValue" in v:
        return bool(v["booleanValue"])
    if "mapValue" in v:
        return {k: _fs_value(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "arrayValue" in v:
        return [_fs_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _fs_fields(doc: dict) -> dict:
    return {k: _fs_value(v) for k, v in doc.get("fields", {}).items()}


def parse_firestore_bars(documents: list) -> pd.DataFrame:
    """Documents markets/{SYM}/years/{AAAA} écrits par la fonction : { bars: [{d,o,h,l,c,v}, ...] }."""
    rows = []
    for doc in documents:
        rows.extend(b for b in _fs_fields(doc).get("bars", []) if isinstance(b, dict))
    if not rows:
        raise DataUnavailable("aucune barre enregistrée (la fonction de mise à jour n'a pas encore rempli la base)")
    df = pd.DataFrame(rows).rename(columns={"d": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    if "volume" not in df.columns:
        df["volume"] = 0.0
    missing = [c for c in ("timestamp", "open", "high", "low", "close") if c not in df.columns]
    if missing:
        raise DataUnavailable(f"documents Firebase incomplets (colonnes manquantes : {missing})")
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def _firebase_hint(exc: Exception) -> str:
    text = str(exc)
    if "404" in text:
        return ("aucune donnée trouvée : Firestore est vide (la fonction de mise à jour n'a pas encore tourné) "
                "ou la base n'est pas créée")
    if "403" in text or "400" in text:
        return "accès refusé : règles Firestore non publiées, ou clé API restreinte (" + text + ")"
    return text


def _closes_to_bars(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")  # "." (jour sans cotation) -> NaN
    df = df.dropna(subset=["close"])

    non_positive = df["close"] <= 0
    if non_positive.any():
        # ex. WTI en avril 2020 : le moteur de backtest suppose des prix > 0
        logger.warning("FRED : %d jour(s) à prix <= 0 écarté(s).", int(non_positive.sum()))
        df = df[~non_positive]
    if df.empty:
        raise DataUnavailable("FRED : aucune donnée exploitable.")

    df = df.reset_index(drop=True)
    df["open"] = df["close"].shift(1).fillna(df["close"])
    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)
    df["volume"] = 0.0
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def parse_twelvedata(payload: dict) -> pd.DataFrame:
    if payload.get("status") == "error" or not isinstance(payload.get("values"), list):
        raise DataUnavailable(f"Twelve Data : {payload.get('message', 'réponse inattendue')}")
    rows = []
    for v in payload["values"]:
        try:
            rows.append({
                "timestamp": str(v["datetime"])[:10],
                "open": float(v["open"]), "high": float(v["high"]),
                "low": float(v["low"]), "close": float(v["close"]),
                "volume": float(v.get("volume") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue  # ligne illisible : ignorée, la validation globale tranchera
    if not rows:
        raise DataUnavailable("Twelve Data : aucune barre exploitable.")
    return pd.DataFrame(rows)


# ---------- Provider ----------

class LiveDataProvider(DataProvider):
    def __init__(self, twelvedata_api_key: str | None = None, ttl_seconds: int = 3600,
                 http_get=_http_get, fred_api_key: str | None = None,
                 firebase_project: str | None = None, firebase_api_key: str | None = None):
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds doit être >= 1")
        self.api_key = twelvedata_api_key or None
        self.fred_api_key = fred_api_key or None
        self.firebase_project = firebase_project or None
        self.firebase_api_key = firebase_api_key or None
        self._firebase_enabled = bool(self.firebase_project and self.firebase_api_key)
        self.ttl_seconds = ttl_seconds
        self._http_get = http_get
        self._cache: dict[str, tuple[float, pd.DataFrame]] = {}
        self._info: dict[str, dict] = {}
        self._lock = threading.RLock()   # une seule récupération à la fois (évite les doublons sous charge)

    # -- API publique --
    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        with self._lock:
            return self._get_ohlcv(symbol)

    def _get_ohlcv(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper()
        if symbol not in ("OIL", "GOLD"):
            raise ValueError(f"Actif inconnu: {symbol}. Disponibles: OIL, GOLD")
        if symbol == "GOLD" and not self.api_key and not self._firebase_enabled:
            raise DataUnavailable(
                "Or : aucune clé TWELVEDATA_API_KEY configurée. Crée une clé gratuite sur "
                "twelvedata.com et ajoute-la dans les secrets de l'application."
            )

        now = time.time()
        cached = self._cache.get(symbol)
        if cached and now - cached[0] < self.ttl_seconds:
            return cached[1].copy()

        try:
            df, source, meta, warning = self._fetch(symbol)
        except Exception as exc:
            msg = _redact(str(exc), self.api_key, self.fred_api_key, self.firebase_api_key)
            if cached:
                logger.warning("%s : mise à jour impossible (%s) — dernière copie servie.", symbol, msg)
                self._info[symbol]["stale_error"] = msg
                return cached[1].copy()
            logger.warning("%s : récupération impossible (%s)", symbol, msg)   # visible dans « Manage app → Logs »
            raise DataUnavailable(f"{symbol} : récupération impossible ({msg}).") from None

        self._cache[symbol] = (now, df)
        self._info[symbol] = {
            "source": source,
            "fetched_at": now,
            "last_date": str(df["timestamp"].iloc[-1].date()),
            "n_bars": len(df),
            "has_volume": bool((df["volume"] > 0).any()),
            "ohlc_approx": bool(meta["ohlcApprox"]) if meta and "ohlcApprox" in meta else symbol == "OIL",
            "stale_error": warning,
        }
        return df.copy()

    def info(self, symbol: str) -> dict:
        return dict(self._info.get(symbol.upper(), {}))

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # -- interne --
    def _fetch_oil(self) -> tuple:
        try:
            df = parse_fred_wti(self._http_get(FRED_WTI_URL).decode("utf-8"))
            return df, "EIA via FRED (DCOILWTICO)"
        except Exception as first:
            reason = f"FRED CSV : {first}"
            if not self.fred_api_key:
                raise DataUnavailable(reason + " — solution : ajoute une clé gratuite FRED_API_KEY "
                                      "(fred.stlouisfed.org) dans les Secrets de l'application.") from None
            logger.warning("%s — essai de l'API officielle FRED.", reason)
            query = urllib.parse.urlencode({"series_id": "DCOILWTICO", "api_key": self.fred_api_key,
                                            "file_type": "json", "observation_start": "2000-01-01"})
            try:
                df = parse_fred_api(json.loads(self._http_get(f"{FRED_API_URL}?{query}")))
            except Exception as second:
                raise DataUnavailable(f"{reason} | FRED API : {second}") from None
            return df, "EIA via FRED API (DCOILWTICO)"

    def _fetch_gold(self) -> tuple:
        if not self.api_key:
            raise DataUnavailable("Or : aucune clé TWELVEDATA_API_KEY configurée (clé gratuite sur twelvedata.com)")
        query = urllib.parse.urlencode({"symbol": "XAU/USD", "interval": "1day", "outputsize": 5000,
                                        "order": "ASC", "apikey": self.api_key})
        raw = self._http_get(f"{TWELVEDATA_URL}?{query}")
        return parse_twelvedata(json.loads(raw)), "Twelve Data (XAU/USD)"

    def _fetch_firebase(self, symbol: str) -> tuple:
        """Lit la base Firestore par l'API REST (règles publiques en lecture seule). Retourne (df, méta)."""
        base = FIRESTORE_URL.format(project=self.firebase_project)
        meta = _fs_fields(json.loads(self._http_get(
            f"{base}/markets/{symbol}?{urllib.parse.urlencode({'key': self.firebase_api_key})}")))
        documents, token = [], None
        for _ in range(10):                                  # pagination (une page = jusqu'à 50 années)
            query = {"pageSize": 50, "key": self.firebase_api_key}
            if token:
                query["pageToken"] = token
            page = json.loads(self._http_get(f"{base}/markets/{symbol}/years?{urllib.parse.urlencode(query)}"))
            documents.extend(page.get("documents", []))
            token = page.get("nextPageToken")
            if not token:
                break
        return parse_firestore_bars(documents), meta

    def _fetch(self, symbol: str) -> tuple:
        """Retourne (DataFrame validé, source, méta Firebase ou None, avertissement ou None).
        Ordre : 1) Firebase (alimentée toutes les heures par la fonction planifiée), 2) lecture directe
        des sources (FRED / Twelve Data). Toutes les raisons d'échec sont conservées pour l'affichage."""
        problems, firebase_copy = [], None
        if self._firebase_enabled:
            try:
                df, meta = self._fetch_firebase(symbol)
                df = validate_ohlcv(df)
                source = "Firebase (" + str(meta.get("source") or "base de données") + ")"
                last = df["timestamp"].iloc[-1]
                if (pd.Timestamp.now(tz="UTC") - last).days <= FIREBASE_MAX_STALE_DAYS:
                    return df, source, meta, None
                problems.append(f"Firebase : données trop anciennes (dernière date {last.date()})")
                firebase_copy = (df, source, meta)
            except Exception as exc:
                problems.append("Firebase : " + _firebase_hint(exc))
        try:
            df, source = self._fetch_oil() if symbol == "OIL" else self._fetch_gold()
            return validate_ohlcv(df), source, None, None
        except Exception as exc:
            problems.append(str(exc))
            if firebase_copy:       # copie Firebase périmée : mieux que rien, mais signalée
                logger.warning("%s : %s", symbol, " | ".join(problems))
                return (*firebase_copy, " | ".join(problems))
            raise DataUnavailable(" | ".join(problems)) from None
