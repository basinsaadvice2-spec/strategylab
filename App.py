"""
StrategyLab — application web 100 % Python (Streamlit), en UN SEUL fichier.
Fichier généré par tools/bundle.py à partir du projet complet : ne pas modifier à la main.
Python fait tout (données, indicateurs, backtest, projection, interface) ; le graphique est TradingView Lightweight Charts.
Simulateur : aucun ordre réel. Un backtest ne garantit jamais la performance future.
"""
import sys
import types

_PACKAGES = ['analysis', 'backtest', 'config', 'data', 'indicators', 'metrics', 'portfolio', 'risk', 'strategy', 'ui']

# Modules du projet, embarqués tels quels, dans leur ordre de chargement.
_SOURCES = {
    'config.settings': """\"\"\"
Paramètres par défaut de StrategyLab.
Aucun secret ici, aucune clé API — voir CLAUDE_STRATEGYLAB_PROMPT.md § Sécurité.
\"\"\"

# --- Actifs disponibles en V1 ---
# Le chemin pointe vers un CSV local (voir data/provider.py). En V1 il n'y a
# pas d'API payante obligatoire : on part de fichiers CSV/Parquet fournis
# par le client ou générés en synthétique pour les démonstrations.
ASSETS = {
    "GOLD": {"label": "Or (Gold)", "path": "synthetic_data/gold_synthetic.csv"},
    "OIL": {"label": "Pétrole (Oil)", "path": "synthetic_data/oil_synthetic.csv"},
}

# --- Périodes standards proposées au client ---
# Le client a précisé qu'il veut choisir parmi des périodes COURANTES
# (pas n'importe quelle fenêtre arbitraire) pour être sûr de la lecture du
# signal, plus une option personnalisée pour affiner.
STANDARD_PERIODS = {
    "1Y": {"label": "1 an", "years": 1},
    "3Y": {"label": "3 ans", "years": 3},
    "5Y": {"label": "5 ans", "years": 5},
    "10Y": {"label": "10 ans", "years": 10},
    # unités plus courtes, utiles pour tester un signal récent
    "3D": {"label": "3 derniers jours", "days": 3},
    "1M": {"label": "1 dernier mois", "days": 30},
    "4M": {"label": "4 derniers mois", "days": 120},
    "CUSTOM": {"label": "Période personnalisée", "custom": True},
}

# --- Fenêtres d'indicateurs standards (pas de valeurs arbitraires par défaut) ---
DEFAULT_INDICATOR_WINDOWS = {
    "SMA_SHORT": 20,
    "SMA_LONG": 50,
    "SMA_TREND": 200,
    "EMA_SHORT": 12,
    "EMA_LONG": 26,
    "RSI": 14,
    "ATR": 14,
    "MACD_FAST": 12,
    "MACD_SLOW": 26,
    "MACD_SIGNAL": 9,
}

# --- Risque / capital ---
DEFAULT_INITIAL_CASH = 10_000.0
DEFAULT_RISK_PCT = 0.02        # 2% du capital risqué par trade
DEFAULT_STOP_LOSS_PCT = 0.02   # distance du stop en % du prix d'entrée
DEFAULT_TAKE_PROFIT_PCT = 0.04

# --- Frais ---
DEFAULT_COMMISSION_RATE = 0.001   # 0.1%
DEFAULT_SLIPPAGE_RATE = 0.0005    # 0.05%

# --- Résolution d'ambiguïté SL/TP intra-bougie ---
# Si le SL et le TP sont tous les deux dans le range [low, high] de la même
# bougie, impossible de savoir lequel a été touché en premier avec des
# données OHLC seules. Politique par défaut = la plus prudente (on suppose
# le pire scénario : le stop est touché avant le take-profit).
SLTP_AMBIGUITY_POLICY = "stop_first"  # "stop_first" | "tp_first" | "flag_only"

# --- Découpage validation ---
# Fractions chronologiques (pas aléatoires — l'ordre temporel est préservé)
SPLIT_DEV_FRACTION = 0.6
SPLIT_VALIDATION_FRACTION = 0.2
# le reste (0.2) est le jeu hors-échantillon, jamais utilisé pour ajuster la stratégie

MIN_TRADES_FOR_RELIABLE_STATS = 20
""",
    'data.loader': """\"\"\"
Chargement + validation/nettoyage des données OHLCV.
Reprend et généralise les corrections faites lors de l'audit du bot V0.2 :
détection des valeurs manquantes, cohérence OHLC, doublons de timestamp
signalés (pas juste supprimés en silence).
\"\"\"
import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED = ["timestamp", "open", "high", "low", "close"]
OPTIONAL = ["volume"]


def load_ohlcv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {path}")

    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    return validate_ohlcv(df)


def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    \"\"\"Contrôles qualité communs à TOUTES les sources (fichier, API, base) :
    une donnée fausse reste fausse même si elle est fraîche. Renvoie un
    DataFrame propre (trié, sans doublon) ou lève ValueError.\"\"\"
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes: {missing}")

    cols = REQUIRED + [c for c in OPTIONAL if c in df.columns]
    df = df[cols].copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="raise")

    if df.empty:
        raise ValueError("Fichier de données vide.")

    # Valeurs manquantes: une cellule vide devient NaN sans lever d'erreur
    # lors de la conversion -> on le détecte nous-mêmes.
    if df[cols].isna().any().any():
        bad = df[cols].columns[df[cols].isna().any()].tolist()
        raise ValueError(f"Valeurs manquantes détectées dans: {bad}")

    # infinités (division par zéro en amont, mauvaise source, etc.)
    import numpy as np
    numeric_cols = [c for c in cols if c != "timestamp"]
    if not np.isfinite(df[numeric_cols].to_numpy()).all():
        raise ValueError("Valeurs infinies (inf/-inf) détectées dans les données.")

    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Les prix doivent être strictement positifs.")
    if "volume" in df.columns and (df["volume"] < 0).any():
        raise ValueError("Le volume ne peut pas être négatif.")

    incoherent = (
        (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
    )
    if incoherent.any():
        raise ValueError(
            f"Données OHLC incohérentes sur {int(incoherent.sum())} ligne(s)."
        )

    if not df["timestamp"].is_monotonic_increasing:
        logger.warning(
            "Timestamps désordonnés dans le fichier source — triés "
            "automatiquement. Vérifier l'export côté fournisseur de données."
        )
    df = df.sort_values("timestamp").reset_index(drop=True)

    dup_mask = df["timestamp"].duplicated(keep="first")
    if dup_mask.any():
        logger.warning(
            "%d timestamp(s) dupliqué(s) détecté(s), écarté(s) (on garde la "
            "première occurrence). Vérifier la source de données.",
            int(dup_mask.sum()),
        )
        df = df[~dup_mask].reset_index(drop=True)

    # Timestamps désordonnés dans le fichier source: on a trié plus haut,
    # mais on le signale car ça indique souvent un problème d'export côté
    # fournisseur de données.
    return df
""",
    'data.provider': """\"\"\"
Couche DataProvider: le moteur de backtest ne sait jamais d'où viennent les
données. En V1 on ne lit que du CSV/Parquet local (pas de cloud, pas d'API
payante), mais une future source (API broker, base de données) n'implique
qu'un nouveau provider respectant cette interface.
\"\"\"
from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd

from data.loader import load_ohlcv


class DataProvider(ABC):
    @abstractmethod
    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        \"\"\"Retourne les données OHLCV complètes et validées pour ce symbole.\"\"\"
        raise NotImplementedError


class CSVDataProvider(DataProvider):
    \"\"\"Charge chaque symbole depuis un chemin CSV/Parquet local configuré
    dans config.settings.ASSETS.\"\"\"

    def __init__(self, asset_map: dict, base_dir: str | Path = "."):
        self.asset_map = asset_map
        self.base_dir = Path(base_dir)
        self._cache: dict[str, pd.DataFrame] = {}

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper()
        if symbol not in self.asset_map:
            raise ValueError(
                f"Actif inconnu: {symbol}. Disponibles: {list(self.asset_map)}"
            )
        if symbol not in self._cache:
            path = self.base_dir / self.asset_map[symbol]["path"]
            self._cache[symbol] = load_ohlcv(path)
        # copie défensive: l'appelant ne doit jamais pouvoir muter le cache
        return self._cache[symbol].copy()
""",
    'data.live_providers': """\"\"\"
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
\"\"\"
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
TWELVEDATA_URL = "https://api.twelvedata.com/time_series"


class DataUnavailable(RuntimeError):
    \"\"\"Source indisponible (réseau, clé manquante, réponse inattendue).\"\"\"


def _http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "StrategyLab/1.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _redact(message: str, secret: str | None) -> str:
    return message.replace(secret, "***") if secret else message


# ---------- Analyse des réponses (fonctions pures, testables hors réseau) ----------

def parse_fred_wti(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text))
    if df.shape[1] < 2:
        raise DataUnavailable("FRED : format de réponse inattendu.")
    df = df.iloc[:, :2].copy()
    df.columns = ["timestamp", "close"]
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
                 http_get=_http_get):
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds doit être >= 1")
        self.api_key = twelvedata_api_key or None
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
        if symbol == "GOLD" and not self.api_key:
            raise DataUnavailable(
                "Or : aucune clé TWELVEDATA_API_KEY configurée. Crée une clé gratuite sur "
                "twelvedata.com et ajoute-la dans les secrets de l'application."
            )

        now = time.time()
        cached = self._cache.get(symbol)
        if cached and now - cached[0] < self.ttl_seconds:
            return cached[1].copy()

        try:
            df = self._fetch(symbol)
        except Exception as exc:
            msg = _redact(str(exc), self.api_key)
            if cached:
                logger.warning("%s : mise à jour impossible (%s) — dernière copie servie.", symbol, msg)
                self._info[symbol]["stale_error"] = msg
                return cached[1].copy()
            raise DataUnavailable(f"{symbol} : récupération impossible ({msg}).") from None

        self._cache[symbol] = (now, df)
        self._info[symbol] = {
            "source": "EIA via FRED (DCOILWTICO)" if symbol == "OIL" else "Twelve Data (XAU/USD)",
            "fetched_at": now,
            "last_date": str(df["timestamp"].iloc[-1].date()),
            "n_bars": len(df),
            "has_volume": bool((df["volume"] > 0).any()),
            "ohlc_approx": symbol == "OIL",
            "stale_error": None,
        }
        return df.copy()

    def info(self, symbol: str) -> dict:
        return dict(self._info.get(symbol.upper(), {}))

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # -- interne --
    def _fetch(self, symbol: str) -> pd.DataFrame:
        if symbol == "OIL":
            raw = self._http_get(FRED_WTI_URL).decode("utf-8")
            df = parse_fred_wti(raw)
        else:
            query = urllib.parse.urlencode({
                "symbol": "XAU/USD", "interval": "1day", "outputsize": 5000,
                "order": "ASC", "apikey": self.api_key,
            })
            raw = self._http_get(f"{TWELVEDATA_URL}?{query}")
            df = parse_twelvedata(json.loads(raw))
        return validate_ohlcv(df)
""",
    'analysis.projection': """\"\"\"
Projection STATISTIQUE (Monte Carlo) — une plage de probabilité, jamais une
prédiction. À partir de la dispersion historique des variations journalières,
on simule des milliers de trajectoires possibles et on lit des percentiles.

Hypothèses (affichées dans l'interface) :
- les variations futures suivent la même dispersion que le passé (peut être faux) ;
- dérive nulle par défaut : le modèle ne prend PAS parti sur la direction
  (hausse/baisse). Sa médiane reste donc proche du dernier prix.
Graine fixe : deux exécutions donnent exactement le même résultat.
\"\"\"
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Projection:
    candles: list      # une "bougie" par mois : open=médiane début, close=médiane fin, high=p90, low=p10
    table: list        # échéances 1/3/6/12 mois : p10, médiane, p90
    sigma_daily: float
    mu_daily: float
    n_paths: int
    seed: int
    bars_per_year: float


def _bars_per_year(timestamps: pd.Series) -> float:
    span_days = (timestamps.iloc[-1] - timestamps.iloc[0]).days
    if span_days <= 0:
        raise ValueError("Historique trop court pour estimer la fréquence des barres.")
    return len(timestamps) / (span_days / 365.25)


def monte_carlo_projection(df: pd.DataFrame, n_months: int = 12, n_paths: int = 2000,
                           seed: int = 42, include_drift: bool = False,
                           lookback_bars: int = 2520) -> Projection:
    \"\"\"`df` : colonnes timestamp, close (trié). `lookback_bars` limite la
    fenêtre d'estimation de la volatilité (par défaut ~10 ans de séances).\"\"\"
    if n_months < 1 or n_paths < 100:
        raise ValueError("n_months >= 1 et n_paths >= 100 requis.")
    d = df[["timestamp", "close"]].tail(lookback_bars).reset_index(drop=True)
    if len(d) < 60:
        raise ValueError("Pas assez d'historique (60 barres minimum) pour une projection.")

    log_ret = np.log(d["close"]).diff().dropna()
    sigma = float(log_ret.std(ddof=1))
    mu = float(log_ret.mean()) if include_drift else 0.0

    bpy = _bars_per_year(d["timestamp"])
    bars_per_month = bpy / 12.0
    horizon = int(round(bars_per_month * n_months))
    rng = np.random.default_rng(seed)
    shocks = rng.normal(mu, sigma, size=(n_paths, horizon))
    last = float(d["close"].iloc[-1])
    paths = np.concatenate(
        [np.full((n_paths, 1), last), last * np.exp(np.cumsum(shocks, axis=1))], axis=1
    )
    p10, p50, p90 = np.percentile(paths, [10, 50, 90], axis=0)

    last_date = d["timestamp"].iloc[-1]
    candles, prev_median = [], last
    for m in range(1, n_months + 1):
        lo_i = int(round(bars_per_month * (m - 1)))
        hi_i = min(int(round(bars_per_month * m)), horizon)
        date = (last_date + pd.DateOffset(months=m)).strftime("%Y-%m-%d")
        candles.append({
            "time": date, "open": round(prev_median, 4), "close": round(float(p50[hi_i]), 4),
            "high": round(float(p90[lo_i:hi_i + 1].max()), 4),
            "low": round(float(p10[lo_i:hi_i + 1].min()), 4),
        })
        prev_median = float(p50[hi_i])

    table = []
    for m in (1, 3, 6, 12):
        if m > n_months:
            continue
        i = min(int(round(bars_per_month * m)), horizon)
        table.append({
            "echeance": f"{m} mois",
            "date": (last_date + pd.DateOffset(months=m)).strftime("%Y-%m-%d"),
            "p10": round(float(p10[i]), 4), "mediane": round(float(p50[i]), 4),
            "p90": round(float(p90[i]), 4),
        })
    return Projection(candles, table, sigma, mu, n_paths, seed, bpy)
""",
    'portfolio.portfolio': """from dataclasses import dataclass


@dataclass
class Position:
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_timestamp: object


class Portfolio:
    \"\"\"Long uniquement en V1 (le cahier des charges ne demande pas le
    short). Une seule position ouverte à la fois.\"\"\"

    def __init__(self, initial_cash: float):
        if initial_cash <= 0:
            raise ValueError("initial_cash doit être strictement positif.")
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.position: Position | None = None

    @property
    def in_position(self) -> bool:
        return self.position is not None

    def open_position(self, quantity: float, entry_price: float,
                       stop_loss: float, take_profit: float, timestamp):
        if self.in_position:
            raise RuntimeError("Une position est déjà ouverte.")
        cost = quantity * entry_price
        if cost > self.cash:
            raise ValueError(
                f"Cash insuffisant: coût {cost:.2f} > cash disponible {self.cash:.2f}."
            )
        self.cash -= cost
        self.position = Position(quantity, entry_price, stop_loss, take_profit, timestamp)

    def close_position(self, exit_price: float) -> float:
        \"\"\"Ferme la position au prix donné, crédite le cash, renvoie le
        produit de la vente (avant frais — les frais sont appliqués par le
        backtest engine, qui connaît le taux de commission).\"\"\"
        if not self.in_position:
            raise RuntimeError("Aucune position ouverte à fermer.")
        proceeds = self.position.quantity * exit_price
        self.cash += proceeds
        self.position = None
        return proceeds

    def equity(self, mark_price: float) -> float:
        if not self.in_position:
            return self.cash
        return self.cash + self.position.quantity * mark_price
""",
    'risk.manager': """from dataclasses import dataclass


@dataclass
class RiskParams:
    risk_pct: float
    stop_loss_pct: float
    take_profit_pct: float

    def __post_init__(self):
        if not (0 < self.risk_pct <= 1):
            raise ValueError("risk_pct doit être dans ]0, 1].")
        if not (0 < self.stop_loss_pct < 1):
            raise ValueError("stop_loss_pct doit être dans ]0, 1[.")
        if not (0 < self.take_profit_pct < 5):
            raise ValueError("take_profit_pct doit être dans ]0, 5[.")

    def stop_loss_price(self, entry_price: float) -> float:
        return entry_price * (1 - self.stop_loss_pct)

    def take_profit_price(self, entry_price: float) -> float:
        return entry_price * (1 + self.take_profit_pct)
""",
    'risk.position_sizing': """\"\"\"
Position sizing basé sur le risque, comme demandé dans le cahier des
charges: "10 000 $ × 2 % = 200 $ de risque théorique par trade si le stop
est exécuté."

quantité = (capital × risque%) / (prix d'entrée × stop_loss%)
\"\"\"


def size_position(cash: float, entry_price: float, risk_pct: float,
                   stop_loss_pct: float) -> tuple[float, float]:
    \"\"\"Retourne (quantité, risque_théorique_dollars).

    La quantité est ensuite plafonnée par le cash réellement disponible côté
    Portfolio (voir portfolio/portfolio.py) — ce module ne connaît que la
    règle de risque, pas l'état du compte.
    \"\"\"
    if cash <= 0:
        raise ValueError("cash doit être positif.")
    if entry_price <= 0:
        raise ValueError("entry_price doit être positif.")
    if not (0 < risk_pct <= 1):
        raise ValueError("risk_pct doit être dans ]0, 1].")
    if not (0 < stop_loss_pct < 1):
        raise ValueError("stop_loss_pct doit être dans ]0, 1[.")

    risk_amount = cash * risk_pct
    stop_distance = entry_price * stop_loss_pct
    quantity = risk_amount / stop_distance
    return quantity, risk_amount
""",
    'backtest.trade': """from dataclasses import dataclass


@dataclass
class Trade:
    entry_time: object
    exit_time: object
    entry_price: float
    exit_price: float
    quantity: float
    fees: float
    pnl_dollars: float
    pnl_pct: float
    exit_reason: str  # "SL" | "TP" | "SIGNAL" | "END_OF_DATA"
    duration_bars: int
    sltp_ambiguous: bool = False
""",
    'backtest.engine': """\"\"\"
Moteur de backtest. Règle absolue (cahier des charges): aucune décision à T
ne peut utiliser une information de T+1 ou après.

Comment c'est garanti ici:
- Les indicateurs et signaux (buy_signal/sell_signal) sont calculés à la
  clôture de la barre T avec des données connues à T.
- L'EXÉCUTION d'un signal a toujours lieu à l'OUVERTURE de la barre T+1,
  jamais sur la clôture de T elle-même.
- Une fois en position, le SL/TP est vérifié barre par barre sur les
  high/low réellement observés, jamais anticipé.
\"\"\"
import pandas as pd

from portfolio.portfolio import Portfolio
from risk.manager import RiskParams
from risk.position_sizing import size_position
from backtest.trade import Trade


class BacktestEngine:
    def __init__(self, initial_cash: float, risk: RiskParams,
                 commission_rate: float, slippage_rate: float,
                 sltp_ambiguity_policy: str = "stop_first"):
        if commission_rate < 0:
            raise ValueError("commission_rate ne peut pas être négatif.")
        if slippage_rate < 0:
            raise ValueError("slippage_rate ne peut pas être négatif.")
        if sltp_ambiguity_policy not in ("stop_first", "tp_first", "flag_only"):
            raise ValueError(
                "sltp_ambiguity_policy doit être stop_first, tp_first ou flag_only."
            )

        self.initial_cash = initial_cash
        self.risk = risk
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.sltp_ambiguity_policy = sltp_ambiguity_policy

    def run(self, df: pd.DataFrame):
        required = {"timestamp", "open", "high", "low", "close", "buy_signal", "sell_signal"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Colonnes manquantes pour le backtest: {missing}")

        portfolio = Portfolio(self.initial_cash)
        trades: list[Trade] = []
        equity_rows = []

        pending_buy = False
        pending_sell_signal = False
        entry_bar_index = None

        n = len(df)
        for i in range(n):
            row = df.iloc[i]

            # --- 1. Exécuter les signaux décidés à la barre précédente ---
            if pending_buy and not portfolio.in_position:
                entry_price = row["open"] * (1 + self.slippage_rate)
                try:
                    qty, _risk_dollars = size_position(
                        portfolio.cash, entry_price,
                        self.risk.risk_pct, self.risk.stop_loss_pct,
                    )
                    max_affordable = portfolio.cash / (entry_price * (1 + self.commission_rate))
                    qty = min(qty, max_affordable)
                    if qty > 0:
                        fee = qty * entry_price * self.commission_rate
                        if qty * entry_price + fee <= portfolio.cash:
                            sl = self.risk.stop_loss_price(entry_price)
                            tp = self.risk.take_profit_price(entry_price)
                            portfolio.cash -= fee  # frais d'entrée prélevés séparément
                            portfolio.open_position(qty, entry_price, sl, tp, row["timestamp"])
                            entry_bar_index = i
                            self._entry_fee = fee
                except ValueError:
                    pass  # cash insuffisant ou paramètres invalides -> pas de trade
            pending_buy = False

            if pending_sell_signal and portfolio.in_position:
                exit_price = row["open"] * (1 - self.slippage_rate)
                self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                   reason="SIGNAL", entry_bar_index=entry_bar_index,
                                   current_bar_index=i)
                entry_bar_index = None
            pending_sell_signal = False

            # --- 2. Vérifier SL/TP intrabar si en position ---
            if portfolio.in_position:
                pos = portfolio.position
                hit_sl = row["low"] <= pos.stop_loss
                hit_tp = row["high"] >= pos.take_profit
                if hit_sl and hit_tp:
                    ambiguous = True
                    if self.sltp_ambiguity_policy == "tp_first":
                        exit_price = pos.take_profit
                        reason = "TP"
                    else:
                        # "stop_first" par défaut (prudent) et "flag_only"
                        # utilisent aussi le stop comme hypothèse par défaut,
                        # mais flag_only marque explicitement l'ambiguïté
                        # pour revue manuelle.
                        exit_price = pos.stop_loss
                        reason = "SL"
                    exit_price *= (1 - self.slippage_rate)
                    self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                       reason=reason, entry_bar_index=entry_bar_index,
                                       current_bar_index=i, ambiguous=ambiguous)
                    entry_bar_index = None
                elif hit_sl:
                    exit_price = pos.stop_loss * (1 - self.slippage_rate)
                    self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                       reason="SL", entry_bar_index=entry_bar_index,
                                       current_bar_index=i)
                    entry_bar_index = None
                elif hit_tp:
                    exit_price = pos.take_profit * (1 - self.slippage_rate)
                    self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                       reason="TP", entry_bar_index=entry_bar_index,
                                       current_bar_index=i)
                    entry_bar_index = None

            # --- 3. Enregistrer l'équité mark-to-market à la clôture ---
            equity_rows.append({
                "timestamp": row["timestamp"],
                "equity": portfolio.equity(row["close"]),
            })

            # --- 4. Décider les actions pour la PROCHAINE barre (pas d'exécution ici) ---
            if not portfolio.in_position and bool(row["buy_signal"]):
                pending_buy = True
            if portfolio.in_position and bool(row["sell_signal"]):
                pending_sell_signal = True

        # Fin des données: si une position reste ouverte, on la clôture au
        # dernier prix connu pour ne pas fausser les statistiques de trades,
        # avec une raison explicite.
        if portfolio.in_position:
            last_row = df.iloc[-1]
            self._close_trade(portfolio, trades, last_row["close"], last_row["timestamp"],
                               reason="END_OF_DATA", entry_bar_index=entry_bar_index,
                               current_bar_index=n - 1)
            equity_rows[-1]["equity"] = portfolio.equity(last_row["close"])

        trades_df = pd.DataFrame([t.__dict__ for t in trades])
        equity_df = pd.DataFrame(equity_rows)
        return trades_df, equity_df

    def _close_trade(self, portfolio: Portfolio, trades: list, exit_price: float,
                      exit_time, reason: str, entry_bar_index: int,
                      current_bar_index: int, ambiguous: bool = False):
        pos = portfolio.position
        entry_fee = getattr(self, "_entry_fee", 0.0)
        exit_fee = pos.quantity * exit_price * self.commission_rate
        proceeds = portfolio.close_position(exit_price)
        portfolio.cash -= exit_fee

        entry_cost = pos.quantity * pos.entry_price
        total_fees = entry_fee + exit_fee
        pnl_dollars = (proceeds - exit_fee) - (entry_cost + entry_fee)
        pnl_pct = (pnl_dollars / (entry_cost + entry_fee)) * 100 if entry_cost > 0 else 0.0
        duration = (current_bar_index - entry_bar_index) if entry_bar_index is not None else 0

        trades.append(Trade(
            entry_time=pos.entry_timestamp,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            fees=total_fees,
            pnl_dollars=pnl_dollars,
            pnl_pct=pnl_pct,
            exit_reason=reason,
            duration_bars=duration,
            sltp_ambiguous=ambiguous,
        ))
        self._entry_fee = 0.0
""",
    'data.periods': """\"\"\"
Résolution des périodes standards demandées par le client (1, 3, 5, 10 ans,
quelques fenêtres courtes utiles, et personnalisée) + découpage chronologique
développement / validation / hors-échantillon.

Le choix explicite de périodes "courantes" plutôt que n'importe quelle
fenêtre arbitraire vient d'une demande directe du client: il veut pouvoir
être sûr de la lecture du signal sur des horizons qu'on utilise
habituellement en pratique, pas fabriquer une fenêtre sur mesure qui
"marche" par hasard.
\"\"\"
from datetime import timedelta
import pandas as pd

from config.settings import STANDARD_PERIODS


def resolve_period(df: pd.DataFrame, period_key: str,
                    custom_start=None, custom_end=None) -> pd.DataFrame:
    \"\"\"Filtre `df` (trié par timestamp) sur la période demandée.

    period_key: une clé de config.settings.STANDARD_PERIODS, ex. "5Y", "3D",
    ou "CUSTOM" avec custom_start/custom_end fournis (str ou Timestamp,
    interprétés en UTC).
    \"\"\"
    if period_key not in STANDARD_PERIODS:
        raise ValueError(
            f"Période inconnue: {period_key}. Disponibles: "
            f"{list(STANDARD_PERIODS)}"
        )
    spec = STANDARD_PERIODS[period_key]

    if spec.get("custom"):
        if custom_start is None or custom_end is None:
            raise ValueError(
                "Période personnalisée: custom_start et custom_end requis."
            )
        start = pd.Timestamp(custom_start, tz="UTC")
        end = pd.Timestamp(custom_end, tz="UTC")
        if start >= end:
            raise ValueError("custom_start doit être avant custom_end.")
    else:
        end = df["timestamp"].max()
        if "years" in spec:
            # approximation calendaire simple, suffisante pour du filtrage
            start = end - pd.DateOffset(years=spec["years"])
        else:
            start = end - timedelta(days=spec["days"])

    out = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].reset_index(drop=True)
    if out.empty:
        raise ValueError(
            f"Aucune donnée dans la période demandée ({period_key}: "
            f"{start.date()} → {end.date()}). Vérifier que les données "
            f"couvrent bien cette plage."
        )
    return out


def chronological_split(df: pd.DataFrame, dev_fraction: float,
                         validation_fraction: float):
    \"\"\"Découpe `df` en trois blocs CONSÉCUTIFS dans le temps (jamais mélangés
    au hasard, l'ordre chronologique est la garantie principale contre le
    data leakage): développement, validation, hors-échantillon.

    Le jeu hors-échantillon ne doit jamais servir à ajuster les paramètres
    de la stratégie — voir CLAUDE_STRATEGYLAB_PROMPT.md § Validation.
    \"\"\"
    if not (0 < dev_fraction < 1) or not (0 < validation_fraction < 1):
        raise ValueError("Les fractions doivent être dans ]0, 1[.")
    if dev_fraction + validation_fraction >= 1:
        raise ValueError(
            "dev_fraction + validation_fraction doit laisser une part "
            "positive pour le hors-échantillon."
        )

    n = len(df)
    i_dev_end = int(n * dev_fraction)
    i_val_end = int(n * (dev_fraction + validation_fraction))

    dev = df.iloc[:i_dev_end].reset_index(drop=True)
    validation = df.iloc[i_dev_end:i_val_end].reset_index(drop=True)
    out_of_sample = df.iloc[i_val_end:].reset_index(drop=True)

    for name, part in [("développement", dev), ("validation", validation),
                        ("hors-échantillon", out_of_sample)]:
        if part.empty:
            raise ValueError(
                f"Le bloc '{name}' est vide avec ce découpage — réduire les "
                f"fractions ou fournir plus de données."
            )
    return dev, validation, out_of_sample
""",
    'indicators.trend': """import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    if span < 1:
        raise ValueError("span doit être >= 1")
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    \"\"\"True sur la barre où `a` vient de croiser `b` par le haut (a était
    <= b la barre précédente, a > b maintenant). N'utilise que des données
    déjà connues à la barre courante — aucun look-ahead.
    \"\"\"
    prev_a, prev_b = a.shift(1), b.shift(1)
    return (prev_a <= prev_b) & (a > b)


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    \"\"\"True sur la barre où `a` vient de croiser `b` par le bas.\"\"\"
    prev_a, prev_b = a.shift(1), b.shift(1)
    return (prev_a >= prev_b) & (a < b)


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    \"\"\"Average Directional Index (Wilder) — force de la tendance,
    indépendamment de sa direction (0 = pas de tendance, >25 = tendance
    marquée). L'un des indicateurs les plus utilisés pour filtrer les
    stratégies de suivi de tendance.\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    high, low, close = df["high"], df["low"], df["close"]
    prev_high, prev_low, prev_close = high.shift(1), low.shift(1), close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move.clip(lower=0)

    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    alpha = 1 / window
    atr_ = tr.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean() / atr_

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=window).mean().astype(float)


def aroon(df: pd.DataFrame, window: int = 25):
    \"\"\"Retourne (aroon_up, aroon_down) — mesure depuis combien de temps
    le plus haut/plus bas de la fenêtre a été atteint (100 = atteint à
    l'instant, 0 = atteint il y a `window` barres).\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")

    def periods_since_extreme(s, agg):
        return s.rolling(window + 1, min_periods=window + 1).apply(
            lambda x: window - (x.argmax() if agg == "max" else x.argmin()), raw=True
        )

    up = 100 * (window - periods_since_extreme(df["high"], "max")) / window
    down = 100 * (window - periods_since_extreme(df["low"], "min")) / window
    return up.astype(float), down.astype(float)
""",
    'indicators.momentum': """import pandas as pd


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    \"\"\"RSI de Wilder. Renvoie NaN pendant la période de préchauffage
    (les `window` premières valeurs), jamais une estimation trompeuse.\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    import numpy as np
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(~(avg_gain.isna() | avg_loss.isna()), np.nan)
    return out.astype(float)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    \"\"\"Retourne (macd_line, signal_line, histogram).\"\"\"
    if fast >= slow:
        raise ValueError("fast doit être < slow")
    ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic(df: pd.DataFrame, k_window: int = 14, d_window: int = 3):
    \"\"\"Retourne (%K, %D). Oscillateur borné [0,100], classique pour
    repérer surachat/survente à court terme.\"\"\"
    if k_window < 1 or d_window < 1:
        raise ValueError("les fenêtres doivent être >= 1")
    low_min = df["low"].rolling(window=k_window, min_periods=k_window).min()
    high_max = df["high"].rolling(window=k_window, min_periods=k_window).max()
    denom = (high_max - low_min).replace(0, pd.NA)
    percent_k = 100 * (df["close"] - low_min) / denom
    percent_d = percent_k.rolling(window=d_window, min_periods=d_window).mean()
    return percent_k.astype(float), percent_d.astype(float)


def williams_r(df: pd.DataFrame, window: int = 14) -> pd.Series:
    \"\"\"Williams %R — inverse du Stochastique, borné [-100, 0].\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    high_max = df["high"].rolling(window=window, min_periods=window).max()
    low_min = df["low"].rolling(window=window, min_periods=window).min()
    denom = (high_max - low_min).replace(0, pd.NA)
    return (-100 * (high_max - df["close"]) / denom).astype(float)


def cci(df: pd.DataFrame, window: int = 20) -> pd.Series:
    \"\"\"Commodity Channel Index. Mesure l'écart du prix typique à sa
    moyenne mobile, normalisé par la déviation moyenne.\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = typical_price.rolling(window=window, min_periods=window).mean()
    import numpy as np
    mean_dev = typical_price.rolling(window=window, min_periods=window).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    denom = (0.015 * mean_dev).replace(0, pd.NA)
    return ((typical_price - sma_tp) / denom).astype(float)


def roc(series: pd.Series, window: int = 12) -> pd.Series:
    \"\"\"Rate of Change — variation en % sur `window` périodes (équivalent
    standard de PCT_CHANGE, nommé différemment car très utilisé sous ce
    nom précis en analyse technique).\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.pct_change(periods=window) * 100


def momentum(series: pd.Series, window: int = 10) -> pd.Series:
    \"\"\"Momentum brut: différence de prix (pas en %) sur `window`
    périodes.\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.diff(periods=window)


def trix(series: pd.Series, window: int = 15) -> pd.Series:
    \"\"\"TRIX: taux de variation d'une triple EMA — filtre le bruit mieux
    qu'un MACD classique, utile sur des tendances de fond.\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    ema1 = series.ewm(span=window, adjust=False, min_periods=window).mean()
    ema2 = ema1.ewm(span=window, adjust=False, min_periods=window).mean()
    ema3 = ema2.ewm(span=window, adjust=False, min_periods=window).mean()
    return ema3.pct_change() * 100


def ultimate_oscillator(df: pd.DataFrame, w1: int = 7, w2: int = 14, w3: int = 28) -> pd.Series:
    \"\"\"Ultimate Oscillator: combine 3 horizons pour réduire les faux
    signaux d'un oscillateur à fenêtre unique.\"\"\"
    prev_close = df["close"].shift(1)
    bp = df["close"] - pd.concat([df["low"], prev_close], axis=1).min(axis=1)
    tr = pd.concat([df["high"], prev_close], axis=1).max(axis=1) - \\
         pd.concat([df["low"], prev_close], axis=1).min(axis=1)

    def avg(w):
        return bp.rolling(w, min_periods=w).sum() / tr.rolling(w, min_periods=w).sum()

    a1, a2, a3 = avg(w1), avg(w2), avg(w3)
    return 100 * (4 * a1 + 2 * a2 + a3) / 7
""",
    'indicators.volatility': """import pandas as pd


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    \"\"\"Average True Range (méthode de Wilder). `df` doit contenir
    high, low, close.\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def bollinger_bands(series: pd.Series, window: int = 20, n_std: float = 2.0):
    \"\"\"Retourne (bande_haute, bande_médiane, bande_basse).\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    middle = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    upper = middle + n_std * std
    lower = middle - n_std * std
    return upper, middle, lower


def bollinger_bandwidth(series: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.Series:
    \"\"\"Largeur des bandes en % du prix — mesure de compression/expansion
    de la volatilité, utile pour détecter les phases de range serré.\"\"\"
    upper, middle, lower = bollinger_bands(series, window, n_std)
    return (upper - lower) / middle * 100


def donchian_channel(df: pd.DataFrame, window: int = 20):
    \"\"\"Retourne (canal_haut, canal_bas): plus haut/plus bas sur `window`
    barres. Base des stratégies de breakout classiques (Turtle Trading).\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    upper = df["high"].rolling(window=window, min_periods=window).max()
    lower = df["low"].rolling(window=window, min_periods=window).min()
    return upper, lower


def keltner_channel(df: pd.DataFrame, ema_window: int = 20, atr_window: int = 10,
                     multiplier: float = 2.0):
    \"\"\"Retourne (canal_haut, canal_bas) basés sur une EMA +/- un multiple
    de l'ATR (moins sensible aux pics isolés que Bollinger).\"\"\"
    from indicators.trend import ema
    middle = ema(df["close"], ema_window)
    band = atr(df, atr_window) * multiplier
    return middle + band, middle - band


def rolling_stddev(series: pd.Series, window: int = 20) -> pd.Series:
    \"\"\"Écart-type glissant du prix — mesure brute de dispersion.\"\"\"
    if window < 1:
        raise ValueError("window doit être >= 1")
    return series.rolling(window=window, min_periods=window).std()
""",
    'indicators.volume': """import pandas as pd


def obv(df: pd.DataFrame) -> pd.Series:
    \"\"\"On-Balance Volume: cumule le volume signé par le sens de la
    clôture. Sert à repérer une divergence entre prix et volume.\"\"\"
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    direction = df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * df["volume"]).cumsum()


def vwap(df: pd.DataFrame, window: int = 20) -> pd.Series:
    \"\"\"Volume Weighted Average Price glissant sur `window` barres (pas
    le VWAP intrajournalier classique, mais son équivalent multi-période,
    plus utile pour un backtest sur barres journalières).\"\"\"
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    if window < 1:
        raise ValueError("window doit être >= 1")
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    return (pv.rolling(window, min_periods=window).sum() /
            df["volume"].rolling(window, min_periods=window).sum())


def mfi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    \"\"\"Money Flow Index — un RSI pondéré par le volume, borné [0,100].\"\"\"
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    if window < 1:
        raise ValueError("window doit être >= 1")
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    raw_money_flow = typical_price * df["volume"]
    direction = typical_price.diff()

    pos_flow = raw_money_flow.where(direction > 0, 0.0)
    neg_flow = raw_money_flow.where(direction < 0, 0.0)

    pos_sum = pos_flow.rolling(window, min_periods=window).sum()
    neg_sum = neg_flow.rolling(window, min_periods=window).sum()

    money_ratio = pos_sum / neg_sum.replace(0, pd.NA)
    return (100 - (100 / (1 + money_ratio))).astype(float)


def cmf(df: pd.DataFrame, window: int = 20) -> pd.Series:
    \"\"\"Chaikin Money Flow — pression acheteuse/vendeuse pondérée par le
    volume, borné [-1, 1].\"\"\"
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    if window < 1:
        raise ValueError("window doit être >= 1")
    range_ = (df["high"] - df["low"]).replace(0, pd.NA)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / range_
    mfv = mfm * df["volume"]
    return (mfv.rolling(window, min_periods=window).sum() /
            df["volume"].rolling(window, min_periods=window).sum())
""",
    'indicators.price': """import pandas as pd


def price(df: pd.DataFrame) -> pd.Series:
    return df["close"]


def pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    if periods < 1:
        raise ValueError("periods doit être >= 1")
    return series.pct_change(periods=periods) * 100


def volume(df: pd.DataFrame) -> pd.Series:
    if "volume" not in df.columns:
        raise ValueError("Colonne volume absente de ces données.")
    return df["volume"]
""",
    'indicators.base': """\"\"\"
Registre d'indicateurs: transforme une spec déclarative (dict) en série
pandas nommée, avec cache pour ne jamais recalculer deux fois le même
indicateur dans une même stratégie. Ajouter un nouvel indicateur = ajouter
une entrée dans _BUILDERS, rien d'autre à toucher.

V1.1: passage de 8 à 26 indicateurs (tendance, momentum, volatilité,
volume) — la liste complète est dans list_available_indicators().
\"\"\"
import pandas as pd

from indicators import trend, momentum, volatility, volume as volume_mod, price as price_mod


def label(spec: dict) -> str:
    \"\"\"Nom de colonne stable et lisible pour une spec d'indicateur.\"\"\"
    name = spec["name"]
    params = spec.get("params", {})
    if name == "CROSSOVER":
        return f"CROSSOVER_{label(params['a'])}_{label(params['b'])}"
    if name == "CROSSUNDER":
        return f"CROSSUNDER_{label(params['a'])}_{label(params['b'])}"
    if not params:
        return name
    parts = "_".join(str(v) for v in params.values())
    return f"{name}_{parts}"


# ---- indicateurs simples (une seule série en sortie) ----
def _build_sma(df, p): return trend.sma(df["close"], p["window"])
def _build_ema(df, p): return trend.ema(df["close"], p["window"])
def _build_rsi(df, p): return momentum.rsi(df["close"], p.get("window", 14))
def _build_atr(df, p): return volatility.atr(df, p.get("window", 14))
def _build_price(df, p): return price_mod.price(df)
def _build_pct_change(df, p): return price_mod.pct_change(df["close"], p.get("periods", 1))
def _build_volume(df, p): return price_mod.volume(df)
def _build_adx(df, p): return trend.adx(df, p.get("window", 14))
def _build_cci(df, p): return momentum.cci(df, p.get("window", 20))
def _build_williams_r(df, p): return momentum.williams_r(df, p.get("window", 14))
def _build_roc(df, p): return momentum.roc(df["close"], p.get("window", 12))
def _build_momentum(df, p): return momentum.momentum(df["close"], p.get("window", 10))
def _build_trix(df, p): return momentum.trix(df["close"], p.get("window", 15))
def _build_ultimate_osc(df, p):
    return momentum.ultimate_oscillator(df, p.get("w1", 7), p.get("w2", 14), p.get("w3", 28))
def _build_bb_bandwidth(df, p):
    return volatility.bollinger_bandwidth(df["close"], p.get("window", 20), p.get("n_std", 2.0))
def _build_stddev(df, p): return volatility.rolling_stddev(df["close"], p.get("window", 20))
def _build_obv(df, p): return volume_mod.obv(df)
def _build_vwap(df, p): return volume_mod.vwap(df, p.get("window", 20))
def _build_mfi(df, p): return volume_mod.mfi(df, p.get("window", 14))
def _build_cmf(df, p): return volume_mod.cmf(df, p.get("window", 20))

def _build_macd_line(df, p):
    line, _, _ = momentum.macd(df["close"], p.get("fast", 12), p.get("slow", 26), p.get("signal", 9))
    return line
def _build_macd_signal(df, p):
    _, sig, _ = momentum.macd(df["close"], p.get("fast", 12), p.get("slow", 26), p.get("signal", 9))
    return sig
def _build_macd_hist(df, p):
    _, _, hist = momentum.macd(df["close"], p.get("fast", 12), p.get("slow", 26), p.get("signal", 9))
    return hist

# ---- indicateurs multi-sortie (paire haute/basse, %K/%D, etc.) ----
def _build_bb_upper(df, p):
    u, _, _ = volatility.bollinger_bands(df["close"], p.get("window", 20), p.get("n_std", 2.0)); return u
def _build_bb_middle(df, p):
    _, m, _ = volatility.bollinger_bands(df["close"], p.get("window", 20), p.get("n_std", 2.0)); return m
def _build_bb_lower(df, p):
    _, _, l = volatility.bollinger_bands(df["close"], p.get("window", 20), p.get("n_std", 2.0)); return l
def _build_donchian_upper(df, p):
    u, _ = volatility.donchian_channel(df, p.get("window", 20)); return u
def _build_donchian_lower(df, p):
    _, l = volatility.donchian_channel(df, p.get("window", 20)); return l
def _build_keltner_upper(df, p):
    u, _ = volatility.keltner_channel(df, p.get("ema_window", 20), p.get("atr_window", 10), p.get("multiplier", 2.0)); return u
def _build_keltner_lower(df, p):
    _, l = volatility.keltner_channel(df, p.get("ema_window", 20), p.get("atr_window", 10), p.get("multiplier", 2.0)); return l
def _build_stoch_k(df, p):
    k, _ = momentum.stochastic(df, p.get("k_window", 14), p.get("d_window", 3)); return k
def _build_stoch_d(df, p):
    _, d = momentum.stochastic(df, p.get("k_window", 14), p.get("d_window", 3)); return d
def _build_aroon_up(df, p):
    u, _ = trend.aroon(df, p.get("window", 25)); return u
def _build_aroon_down(df, p):
    _, d = trend.aroon(df, p.get("window", 25)); return d


_BUILDERS = {
    "SMA": _build_sma, "EMA": _build_ema, "RSI": _build_rsi, "ATR": _build_atr,
    "PRICE": _build_price, "PCT_CHANGE": _build_pct_change, "VOLUME": _build_volume,
    "MACD_LINE": _build_macd_line, "MACD_SIGNAL": _build_macd_signal, "MACD_HIST": _build_macd_hist,
    "ADX": _build_adx, "CCI": _build_cci, "WILLIAMS_R": _build_williams_r,
    "ROC": _build_roc, "MOMENTUM": _build_momentum, "TRIX": _build_trix,
    "ULTIMATE_OSC": _build_ultimate_osc, "BB_BANDWIDTH": _build_bb_bandwidth,
    "STDDEV": _build_stddev, "OBV": _build_obv, "VWAP": _build_vwap,
    "MFI": _build_mfi, "CMF": _build_cmf,
    "BB_UPPER": _build_bb_upper, "BB_MIDDLE": _build_bb_middle, "BB_LOWER": _build_bb_lower,
    "DONCHIAN_UPPER": _build_donchian_upper, "DONCHIAN_LOWER": _build_donchian_lower,
    "KELTNER_UPPER": _build_keltner_upper, "KELTNER_LOWER": _build_keltner_lower,
    "STOCH_K": _build_stoch_k, "STOCH_D": _build_stoch_d,
    "AROON_UP": _build_aroon_up, "AROON_DOWN": _build_aroon_down,
}


_VOLUME_BASED = {"VOLUME", "OBV", "VWAP", "MFI", "CMF"}


def list_available_indicators() -> list:
    \"\"\"Utilisé par l'UI (Streamlit) pour peupler les listes déroulantes.\"\"\"
    return sorted(_BUILDERS) + ["CROSSOVER", "CROSSUNDER"]


class IndicatorEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._cache: dict[str, pd.Series] = {}

    def get(self, spec: dict) -> pd.Series:
        key = label(spec)
        if key in self._cache:
            return self._cache[key]

        name = spec["name"]
        params = spec.get("params", {})

        if name == "CROSSOVER":
            a = self.get(params["a"])
            b = self.get(params["b"])
            out = trend.crossover(a, b)
        elif name == "CROSSUNDER":
            a = self.get(params["a"])
            b = self.get(params["b"])
            out = trend.crossunder(a, b)
        elif name in _BUILDERS:
            if name in _VOLUME_BASED and "volume" in self.df.columns \\
                    and not (self.df["volume"] > 0).any():
                # Aucun volume réel (ex. pétrole : clôtures journalières seules) :
                # ces indicateurs n'ont alors aucun sens -> NaN partout, donc
                # jamais de signal (plutôt que des valeurs trompeuses comme OBV = 0).
                out = pd.Series(float("nan"), index=self.df.index)
            else:
                out = _BUILDERS[name](self.df, params)
        else:
            raise ValueError(
                f"Indicateur inconnu: {name}. Disponibles: {list_available_indicators()}"
            )

        self._cache[key] = out
        return out
""",
    'metrics.report': """import numpy as np
import pandas as pd

from config.settings import MIN_TRADES_FOR_RELIABLE_STATS


def build_report(trades: pd.DataFrame, equity: pd.DataFrame, initial_cash: float,
                  asset: str, period_label: str, commission_rate: float,
                  slippage_rate: float) -> dict:
    if initial_cash <= 0:
        raise ValueError("initial_cash doit être strictement positif.")

    final_equity = float(equity["equity"].iloc[-1]) if not equity.empty else initial_cash
    return_pct = (final_equity / initial_cash - 1) * 100

    if equity.empty:
        max_dd = 0.0
    else:
        peak = equity["equity"].cummax()
        max_dd = float(((equity["equity"] / peak - 1) * 100).min())

    n_trades = len(trades)
    if n_trades > 0:
        wins = trades[trades["pnl_dollars"] > 0]
        losses = trades[trades["pnl_dollars"] < 0]
        win_rate = 100 * len(wins) / n_trades
        avg_win = float(wins["pnl_dollars"].mean()) if len(wins) else 0.0
        avg_loss = float(losses["pnl_dollars"].mean()) if len(losses) else 0.0
        gross_profit = float(wins["pnl_dollars"].sum())
        gross_loss = abs(float(losses["pnl_dollars"].sum()))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else None
        )
        expectancy = float(trades["pnl_dollars"].mean())
        total_fees = float(trades["fees"].sum())
        avg_duration_bars = float(trades["duration_bars"].mean())
        n_ambiguous = int(trades["sltp_ambiguous"].sum())
    else:
        win_rate = avg_win = avg_loss = expectancy = total_fees = avg_duration_bars = 0.0
        profit_factor = None
        n_ambiguous = 0

    report = {
        "asset": asset,
        "period": period_label,
        "initial_cash": initial_cash,
        "final_equity": final_equity,
        "return_pct": return_pct,
        "max_drawdown_pct": max_dd,
        "n_trades": n_trades,
        "n_wins": int((trades["pnl_dollars"] > 0).sum()) if n_trades else 0,
        "n_losses": int((trades["pnl_dollars"] < 0).sum()) if n_trades else 0,
        "win_rate_pct": win_rate,
        "avg_win_dollars": avg_win,
        "avg_loss_dollars": avg_loss,
        "profit_factor": profit_factor,
        "expectancy_dollars": expectancy,
        "total_fees_dollars": total_fees,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
        "avg_trade_duration_bars": avg_duration_bars,
        "sltp_ambiguous_trades": n_ambiguous,
        "reliable_sample": n_trades >= MIN_TRADES_FOR_RELIABLE_STATS,
        "disclaimer": (
            "Résultats descriptifs sur données historiques. Ceci ne "
            "constitue en aucun cas une garantie de performance future."
        ),
    }
    return report
""",
    'strategy.conditions': """\"\"\"
Une condition compare un indicateur à un seuil numérique OU à un autre
indicateur (ex: "prix > SMA 200"). Pas de code à écrire côté client — tout
est déclaratif (dict), ce qui permet de construire l'écran "Strategy
Builder" sans exposer Python à l'utilisateur final.
\"\"\"
import operator as _op
import pandas as pd

from indicators.base import IndicatorEngine

_OPERATORS = {
    ">": _op.gt,
    "<": _op.lt,
    ">=": _op.ge,
    "<=": _op.le,
    "=": _op.eq,
}


def evaluate_condition(engine: IndicatorEngine, condition: dict) -> pd.Series:
    op_symbol = condition["operator"]
    if op_symbol not in _OPERATORS:
        raise ValueError(
            f"Opérateur inconnu: {op_symbol}. Disponibles: {list(_OPERATORS)}"
        )

    left = engine.get(condition["left"])

    right = condition["right"]
    if isinstance(right, dict):
        right = engine.get(right)
    elif not isinstance(right, (int, float)):
        raise ValueError(
            "`right` doit être un nombre ou une spec d'indicateur (dict)."
        )

    result = _OPERATORS[op_symbol](left, right)
    # Toute ligne où l'indicateur n'est pas encore défini (préchauffage,
    # ex. RSI avant `window` barres) ne doit jamais déclencher un signal.
    result = result.fillna(False)
    return result
""",
    'strategy.rules': """import pandas as pd

from indicators.base import IndicatorEngine
from strategy.conditions import evaluate_condition

_LOGIC = {"AND", "OR"}


def evaluate_rule(engine: IndicatorEngine, rule: dict) -> pd.Series:
    \"\"\"rule = {"logic": "AND" | "OR", "conditions": [condition, ...]}\"\"\"
    logic = rule.get("logic", "AND")
    if logic not in _LOGIC:
        raise ValueError(f"logic doit être AND ou OR, reçu: {logic}")

    conditions = rule.get("conditions", [])
    if not conditions:
        raise ValueError("Une règle doit contenir au moins une condition.")

    results = [evaluate_condition(engine, c) for c in conditions]

    combined = results[0]
    for r in results[1:]:
        combined = (combined & r) if logic == "AND" else (combined | r)
    return combined
""",
    'strategy.builder': """import pandas as pd

from indicators.base import IndicatorEngine
from strategy.rules import evaluate_rule


class StrategyBuilder:
    \"\"\"Construit les colonnes buy_signal / sell_signal à partir de règles
    déclaratives. N'exécute rien — c'est le rôle du backtest engine.

    Exemple (correspond à celui du cahier des charges):
        buy_rule = {
            "logic": "AND",
            "conditions": [
                {"left": {"name": "RSI", "params": {"window": 14}},
                 "operator": "<", "right": 30},
                {"left": {"name": "PRICE"}, "operator": ">",
                 "right": {"name": "SMA", "params": {"window": 200}}},
            ],
        }
    \"\"\"

    def __init__(self, buy_rule: dict, sell_rule: dict):
        self.buy_rule = buy_rule
        self.sell_rule = sell_rule

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        engine = IndicatorEngine(df)
        out = df.copy()
        out["buy_signal"] = evaluate_rule(engine, self.buy_rule)
        out["sell_signal"] = evaluate_rule(engine, self.sell_rule)
        return out
""",
    'ui.tv_chart': """\"\"\"
Graphique "à la TradingView" : bibliothèque open source Lightweight Charts™ de
TradingView (Apache-2.0), version 4.2.0 figée. Elle ne fait que DESSINER : toutes
les données et tous les calculs viennent de Python.

Licence : l'attribution à TradingView (lien vers tradingview.com) est obligatoire ;
elle est affichée sous le graphique. Pour la conformité stricte, reprends le texte
exact du fichier NOTICE du dépôt github.com/tradingview/lightweight-charts.

Séries journalières uniquement (temps = "AAAA-MM-JJ").
\"\"\"
import json
import math

import pandas as pd

LWC_URL = "https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"

THEME = {
    "bg": "#131722", "grid": "#1e222d", "text": "#d1d4dc", "up": "#089981", "down": "#f23645",
    "sma_fast": "#ff9800", "sma_slow": "#2962ff", "rsi": "#7e57c2", "proj": "#ff9800",
}


def _day(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _num(x, nd=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def df_to_candles(df: pd.DataFrame) -> list:
    return [{"time": _day(r.timestamp), "open": _num(r.open), "high": _num(r.high),
             "low": _num(r.low), "close": _num(r.close)} for r in df.itertuples()]


def df_to_volume(df: pd.DataFrame) -> list:
    \"\"\"Vide si l'actif n'a pas de volume réel (ex. pétrole).\"\"\"
    if "volume" not in df.columns or not (df["volume"] > 0).any():
        return []
    up, down = THEME["up"] + "66", THEME["down"] + "66"
    return [{"time": _day(r.timestamp), "value": _num(r.volume, 0),
             "color": up if r.close >= r.open else down} for r in df.itertuples()]


def series_to_line(df: pd.DataFrame, column: str) -> list:
    \"\"\"Une entrée par barre : les valeurs manquantes (préchauffage) deviennent des
    points "vides" ({time} seul) afin que tous les graphiques gardent exactement les
    mêmes positions et restent synchronisés.\"\"\"
    out = []
    for t, v in zip(df["timestamp"], df[column]):
        val = _num(v)
        out.append({"time": _day(t)} if val is None else {"time": _day(t), "value": val})
    return out


_REASON = {"SL": "Stop", "TP": "Objectif", "SIGNAL": "Signal", "END_OF_DATA": "Fin"}


def trades_to_markers(trades: pd.DataFrame) -> list:
    \"\"\"Flèches d'achat (vertes, sous la bougie) et de vente (rouges, au-dessus), triées par date.\"\"\"
    markers = []
    for t in trades.itertuples():
        markers.append({"time": _day(t.entry_time), "position": "belowBar",
                        "color": THEME["up"], "shape": "arrowUp", "text": "Achat"})
        sign = "+" if t.pnl_dollars >= 0 else "−"
        markers.append({"time": _day(t.exit_time), "position": "aboveBar",
                        "color": THEME["down"], "shape": "arrowDown",
                        "text": f"{_REASON.get(t.exit_reason, t.exit_reason)} {sign}{abs(t.pnl_dollars):.0f}$"})
    markers.sort(key=lambda m: m["time"])
    return markers


def projection_candles(candles: list) -> list:
    \"\"\"Bougies projetées (une par mois), en ambre translucide pour ne jamais les
    confondre avec de vraies bougies.\"\"\"
    out = []
    for c in candles:
        out.append({**c, "color": "rgba(245,158,11,0.35)", "borderColor": THEME["proj"],
                    "wickColor": THEME["proj"]})
    return out


# Fonction JS réutilisable : dessine (ou redessine) un graphique prix + RSI optionnel.
# Utilisée par la page à un seul graphique (build_chart_html) ET par la page d'aperçu interactive.
RENDER_JS = \"\"\"
window.renderTV = function (P, T, els) {
  const LC = window.LightweightCharts;
  els.legend.textContent = '';
  if (!LC) {
    els.legend.textContent = 'Bibliothèque graphique non chargée (connexion internet requise).';
    return { destroy: function () {}, resize: function () {} };
  }
  const base = {
    layout: { background: { type: 'solid', color: T.bg }, textColor: T.text },
    grid: { vertLines: { color: T.grid }, horzLines: { color: T.grid } },
    rightPriceScale: { borderColor: T.grid },
    timeScale: { borderColor: T.grid, rightOffset: 4 },
    crosshair: { mode: LC.CrosshairMode.Normal },
  };
  const mainEl = els.main;
  // Logo d'attribution TradingView intégré (option attributionLogo, disponible depuis la v4.2.0)
  const main = LC.createChart(mainEl, Object.assign({ width: mainEl.clientWidth, height: mainEl.clientHeight }, base,
    { layout: Object.assign({}, base.layout, { attributionLogo: true }) }));

  const candles = main.addCandlestickSeries({
    upColor: T.up, downColor: T.down, wickUpColor: T.up, wickDownColor: T.down, borderVisible: false,
  });
  candles.setData(P.candles);
  if (P.markers && P.markers.length) candles.setMarkers(P.markers);

  if (P.volume && P.volume.length) {
    const vol = main.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol' });
    main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(P.volume);
  }
  (P.overlays || []).forEach(function (o) {
    const s = main.addLineSeries({ color: o.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    s.setData(o.data);
  });

  const charts = [main], rsiEl = els.rsi;
  const withRsi = !!(P.rsi && P.rsi.length && rsiEl);
  if (els.rsilabel) els.rsilabel.style.display = withRsi ? 'block' : 'none';
  if (rsiEl) rsiEl.style.display = withRsi ? 'block' : 'none';
  if (withRsi) {
    const rsiChart = LC.createChart(rsiEl, Object.assign({ width: rsiEl.clientWidth, height: rsiEl.clientHeight }, base));
    const line = rsiChart.addLineSeries({
      color: T.rsi, lineWidth: 2, priceLineVisible: false,
      autoscaleInfoProvider: function () { return { priceRange: { minValue: 0, maxValue: 100 } }; },
    });
    line.setData(P.rsi);
    [30, 70].forEach(function (lvl) {
      line.createPriceLine({ price: lvl, color: '#64748b', lineWidth: 1, lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true, title: '' });
    });
    charts.push(rsiChart);
  }

  // Défilement / zoom synchronisés entre le prix et le RSI
  let busy = false;
  charts.forEach(function (src) {
    src.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
      if (busy || !range) return;
      busy = true;
      charts.forEach(function (dst) { if (dst !== src) dst.timeScale().setVisibleLogicalRange(range); });
      busy = false;
    });
  });
  charts.forEach(function (c) { c.timeScale().fitContent(); });

  // Légende façon TradingView : titre + OHLC sous le curseur
  const last = P.candles.length ? P.candles[P.candles.length - 1] : null;
  function fmt(x) { return (typeof x === 'number') ? x.toFixed(2) : '–'; }
  function show(d) {
    els.legend.textContent = '';
    const b = document.createElement('b'); b.textContent = P.title || ''; els.legend.appendChild(b);
    if (d) els.legend.appendChild(document.createTextNode('  O ' + fmt(d.open) + '  H ' + fmt(d.high) + '  L ' + fmt(d.low) + '  C ' + fmt(d.close)));
  }
  show(last);
  main.subscribeCrosshairMove(function (param) {
    const d = param && param.seriesData ? param.seriesData.get(candles) : null;
    show(d || last);
  });

  return {
    destroy: function () { charts.forEach(function (c) { c.remove(); }); },
    resize: function () {
      charts.forEach(function (c, i) { var el = (i === 0 ? mainEl : rsiEl); c.applyOptions({ width: el.clientWidth, height: el.clientHeight }); });
    },
  };
};
\"\"\"


def build_chart_html(payload: dict, height_main: int = 430, height_rsi: int = 150) -> str:
    \"\"\"payload : title, candles, [volume], [overlays: [{name,color,data}]], [markers],
    [rsi]. Retourne une page HTML autonome (à passer à streamlit.components.v1.html).\"\"\"
    data = json.dumps({**payload, "theme": THEME}, ensure_ascii=False).replace("<", "\\\\u003c")
    return (_TEMPLATE
            .replace("__LWC_URL__", LWC_URL)
            .replace("__RENDER_JS__", RENDER_JS)
            .replace("__PAYLOAD__", data)
            .replace("__H_MAIN__", str(int(height_main)))
            .replace("__H_RSI__", str(int(height_rsi)))
            .replace("__BG__", THEME["bg"]).replace("__TEXT__", THEME["text"]))


_TEMPLATE = \"\"\"<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin:0; background:__BG__; color:__TEXT__; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; }
  #wrap { position:relative; }
  #legend { position:absolute; top:8px; left:10px; z-index:5; font-size:12px; line-height:1.5; pointer-events:none; }
  #legend b { color:#e6edf7; font-size:13px; }
  #main { height:__H_MAIN__px; }
  #rsi { height:__H_RSI__px; margin-top:2px; }
  #rsilabel { font-size:11px; padding:4px 10px 0; }
  #attr { font-size:11px; padding:6px 10px 8px; opacity:.85; }
  #attr a { color:#7aa2ff; text-decoration:none; }
</style></head><body>
<div id="wrap"><div id="legend"></div><div id="main"></div></div>
<div id="rsilabel" style="display:none">RSI (14) — surachat au-dessus de 70, survente en dessous de 30</div>
<div id="rsi" style="display:none"></div>
<div id="attr">Graphiques : <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a> · Copyright © TradingView, Inc.</div>
<script src="__LWC_URL__"></script>
<script>__RENDER_JS__</script>
<script>
(function () {
  const P = __PAYLOAD__;
  const h = window.renderTV(P, P.theme, {
    main: document.getElementById('main'), rsi: document.getElementById('rsi'),
    rsilabel: document.getElementById('rsilabel'), legend: document.getElementById('legend'),
  });
  window.addEventListener('resize', function () { h.resize(); });
})();
</script></body></html>
\"\"\"
""",
    'ui.app_logic': """\"\"\"
Logique de l'application, SANS Streamlit (donc testable sans interface).
L'écran Streamlit (ui/streamlit_app.py) ne fait que l'afficher.
\"\"\"
import math

import pandas as pd

from analysis.projection import monte_carlo_projection
from backtest.engine import BacktestEngine
from config.settings import SLTP_AMBIGUITY_POLICY, STANDARD_PERIODS
from data.periods import resolve_period
from indicators.base import IndicatorEngine
from metrics.report import build_report
from risk.manager import RiskParams
from strategy.builder import StrategyBuilder
from ui import tv_chart

OPERATORS = [">", "<", ">=", "<=", "="]


def _spec(name, **params):
    return {"name": name, "params": params}


INDICATOR_CHOICES = {
    "Prix": _spec("PRICE"),
    "RSI (14)": _spec("RSI", window=14),
    "SMA 20": _spec("SMA", window=20), "SMA 50": _spec("SMA", window=50), "SMA 200": _spec("SMA", window=200),
    "EMA 12": _spec("EMA", window=12), "EMA 26": _spec("EMA", window=26),
    "Variation % (5 jours)": _spec("PCT_CHANGE", periods=5),
    "MACD ligne": _spec("MACD_LINE"), "MACD signal": _spec("MACD_SIGNAL"), "MACD histogramme": _spec("MACD_HIST"),
    "Stochastique %K": _spec("STOCH_K"), "Stochastique %D": _spec("STOCH_D"),
    "Williams %R": _spec("WILLIAMS_R", window=14), "CCI (20)": _spec("CCI", window=20),
    "ADX (14)": _spec("ADX", window=14), "Aroon haut": _spec("AROON_UP", window=25),
    "Aroon bas": _spec("AROON_DOWN", window=25), "ROC (12)": _spec("ROC", window=12),
    "Momentum (10)": _spec("MOMENTUM", window=10), "TRIX (15)": _spec("TRIX", window=15),
    "Ultimate Oscillator": _spec("ULTIMATE_OSC"), "ATR (14)": _spec("ATR", window=14),
    "Bollinger haute": _spec("BB_UPPER", window=20), "Bollinger basse": _spec("BB_LOWER", window=20),
    "Bollinger largeur %": _spec("BB_BANDWIDTH", window=20),
    "Donchian haut": _spec("DONCHIAN_UPPER", window=20), "Donchian bas": _spec("DONCHIAN_LOWER", window=20),
    "Keltner haut": _spec("KELTNER_UPPER"), "Keltner bas": _spec("KELTNER_LOWER"),
    "Écart-type (20)": _spec("STDDEV", window=20),
    "Volume": _spec("VOLUME"), "OBV": _spec("OBV"), "VWAP (20)": _spec("VWAP", window=20),
    "MFI (14)": _spec("MFI", window=14), "CMF (20)": _spec("CMF", window=20),
}


def make_condition(left_label: str, operator: str, mode: str, value=None, right_label: str | None = None) -> dict:
    \"\"\"mode = 'Valeur' (seuil numérique) ou 'Indicateur' (comparaison à un autre indicateur).\"\"\"
    if left_label not in INDICATOR_CHOICES:
        raise ValueError(f"Indicateur inconnu: {left_label}")
    if operator not in OPERATORS:
        raise ValueError(f"Opérateur inconnu: {operator}")
    if mode == "Valeur":
        if value is None:
            raise ValueError("Un seuil numérique est requis.")
        right = float(value)
    elif mode == "Indicateur":
        if right_label not in INDICATOR_CHOICES:
            raise ValueError(f"Indicateur de comparaison inconnu: {right_label}")
        right = INDICATOR_CHOICES[right_label]
    else:
        raise ValueError(f"Mode inconnu: {mode}")
    return {"left": INDICATOR_CHOICES[left_label], "operator": operator, "right": right}


def make_rule(logic: str, conditions: list) -> dict:
    return {"logic": logic, "conditions": conditions}


def run_analysis(full_df: pd.DataFrame, period_key: str, buy_rule: dict, sell_rule: dict,
                 cash: float, risk_pct: float, stop_loss_pct: float, take_profit_pct: float,
                 commission_rate: float, slippage_rate: float, asset_label: str = "",
                 custom_start=None, custom_end=None) -> dict:
    df = full_df.copy()

    # Indicateurs d'affichage ET signaux calculés sur TOUT l'historique, puis découpe de
    # la période : un indicateur long (SMA 200) reste donc défini même sur une période courte.
    ind = IndicatorEngine(df)
    df["SMA20"] = ind.get(_spec("SMA", window=20))
    df["SMA50"] = ind.get(_spec("SMA", window=50))
    df["RSI14"] = ind.get(_spec("RSI", window=14))
    df = StrategyBuilder(buy_rule, sell_rule).apply(df)
    period_df = resolve_period(df, period_key, custom_start, custom_end)

    risk = RiskParams(risk_pct, stop_loss_pct, take_profit_pct)
    bt = BacktestEngine(cash, risk, commission_rate, slippage_rate, SLTP_AMBIGUITY_POLICY)
    trades, equity = bt.run(period_df)
    report = build_report(trades, equity, cash, asset_label, STANDARD_PERIODS[period_key]["label"],
                          commission_rate, slippage_rate)

    payload = {
        "title": f"{asset_label} · {STANDARD_PERIODS[period_key]['label']}",
        "candles": tv_chart.df_to_candles(period_df),
        "volume": tv_chart.df_to_volume(period_df),
        "overlays": [
            {"name": "SMA 20", "color": tv_chart.THEME["sma_fast"], "data": tv_chart.series_to_line(period_df, "SMA20")},
            {"name": "SMA 50", "color": tv_chart.THEME["sma_slow"], "data": tv_chart.series_to_line(period_df, "SMA50")},
        ],
        "markers": tv_chart.trades_to_markers(trades),
        "rsi": tv_chart.series_to_line(period_df, "RSI14"),
    }
    return {"period_df": period_df, "trades": trades, "equity": equity, "report": report,
            "chart_payload": payload}


def projection_view(full_df: pd.DataFrame, title: str, n_history: int = 90, n_months: int = 12) -> dict:
    proj = monte_carlo_projection(full_df, n_months=n_months)
    history = tv_chart.df_to_candles(full_df.tail(n_history))
    payload = {"title": f"{title} · projection statistique", "candles": history + tv_chart.projection_candles(proj.candles)}
    return {"payload": payload, "table": proj.table, "sigma_daily": proj.sigma_daily,
            "n_paths": proj.n_paths, "seed": proj.seed}


def chart_height(payload: dict, height_main: int = 430, height_rsi: int = 150) -> int:
    \"\"\"Hauteur totale à réserver pour le composant HTML (prix + RSI éventuel + légendes).\"\"\"
    return height_main + (height_rsi + 24 if payload.get("rsi") else 0) + 40


def summarize(res: dict, stop_loss_pct: float, slippage_rate: float) -> dict:
    \"\"\"Chiffres complémentaires à build_report : ratio de Sharpe (annualisé sur 252 séances), slippage
    estimé en dollars, sorties par type et lignes de trades avec leur multiple de risque R
    (résultat ÷ risque au stop). Partagé par l'API et l'application Streamlit.\"\"\"
    trades, equity = res["trades"], res["equity"]
    returns = equity["equity"].pct_change().dropna()
    sharpe = (float(returns.mean() / returns.std() * math.sqrt(252)) if len(returns) > 2 and returns.std() > 0 else None)
    rows, reasons, slip_cost = [], {}, 0.0
    for t in trades.itertuples():
        risk_at_stop = t.quantity * t.entry_price * stop_loss_pct
        rows.append({
            "entry": pd.Timestamp(t.entry_time).strftime("%Y-%m-%d"), "exit": pd.Timestamp(t.exit_time).strftime("%Y-%m-%d"),
            "entry_price": round(float(t.entry_price), 4), "exit_price": round(float(t.exit_price), 4),
            "quantity": round(float(t.quantity), 4), "pnl": round(float(t.pnl_dollars), 2),
            "pnl_pct": round(float(t.pnl_pct), 2), "reason": str(t.exit_reason),
            "r": round(float(t.pnl_dollars) / risk_at_stop, 2) if risk_at_stop > 0 else None,
        })
        reasons[str(t.exit_reason)] = reasons.get(str(t.exit_reason), 0) + 1
        slip_cost += slippage_rate * t.quantity * (t.entry_price + t.exit_price)
    return {"sharpe_ratio": sharpe, "slippage_estimated_dollars": round(slip_cost, 2), "exit_reasons": reasons, "trade_rows": rows}
""",
}


def _install():
    for pkg in _PACKAGES:
        if pkg not in sys.modules:
            module = types.ModuleType(pkg)
            module.__path__ = []
            sys.modules[pkg] = module
    for name, source in _SOURCES.items():
        if name in sys.modules:          # Streamlit relance le script à chaque interaction : on ne recharge pas
            continue
        module = types.ModuleType(name)
        module.__file__ = "<strategylab:" + name + ">"
        module.__package__ = name.rpartition(".")[0]
        sys.modules[name] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        setattr(sys.modules[module.__package__], name.rpartition(".")[2], module)


_install()

# ===================================================================== APPLICATION
import json
import os
import sys


import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config.settings import (
    DEFAULT_COMMISSION_RATE, DEFAULT_INITIAL_CASH, DEFAULT_RISK_PCT, DEFAULT_SLIPPAGE_RATE,
    DEFAULT_STOP_LOSS_PCT, DEFAULT_TAKE_PROFIT_PCT, STANDARD_PERIODS,
)
from data.live_providers import DataUnavailable, LiveDataProvider
from ui import app_logic as logic
from ui import tv_chart

st.set_page_config(page_title="StrategyLab", page_icon="📈", layout="wide")
st.markdown("""<style>
.stApp { background:#131722; color:#d1d4dc; }
[data-testid="stHeader"] { background:#131722; }
[data-testid="stSidebar"] { background:#1e222d; border-right:1px solid #2a2e39; }
.block-container { padding-top:1.2rem; max-width:none; }
h1, h2, h3, h4, label, p, span { color:inherit; }
[data-testid="stMetric"] { background:#1e222d; border-radius:4px; padding:8px 12px; }
[data-testid="stMetricLabel"] { color:#787b86; }
.stTabs [data-baseweb="tab"] { color:#787b86; } .stTabs [aria-selected="true"] { color:#d1d4dc; }
[data-testid="stRadio"] [role="radiogroup"] { gap:4px; }
.sl-title { font-size:20px; font-weight:700; } .sl-sub { color:#787b86; font-size:12px; }
</style>""", unsafe_allow_html=True)

ASSET_LABELS = {"OIL": "Pétrole (WTI)", "GOLD": "Or (XAU/USD)"}
PERIOD_ORDER = ["3D", "1M", "4M", "1Y", "3Y", "5Y", "10Y", "CUSTOM"]
PERIOD_SHORT = {"3D": "3J", "1M": "1M", "4M": "4M", "1Y": "1A", "3Y": "3A", "5Y": "5A", "10Y": "10A", "CUSTOM": "Perso."}
REASONS = {"SL": "Stop", "TP": "Objectif", "SIGNAL": "Signal", "END_OF_DATA": "Fin"}
DEFAULT_BUY = [("RSI (14)", "<", "Valeur", 30.0, "Prix"), ("Prix", ">", "Indicateur", 0.0, "SMA 200")]
DEFAULT_SELL = [("RSI (14)", ">", "Valeur", 70.0, "Prix"), ("Prix", "<", "Indicateur", 0.0, "SMA 200")]


def _secret(name: str):
    try:
        value = st.secrets.get(name)
    except Exception:  # aucun fichier de secrets configuré
        value = None
    return value or os.environ.get(name)


@st.cache_resource
def get_provider() -> LiveDataProvider:
    # Un seul fournisseur partagé : une récupération par heure pour tous les visiteurs.
    return LiveDataProvider(twelvedata_api_key=_secret("TWELVEDATA_API_KEY"), ttl_seconds=3600)


@st.cache_data(ttl=3600, show_spinner="Analyse en cours…")
def analyse(asset, period_key, c_start, c_end, cash, risk, sl, tp, com, slip, buy_json, sell_json):
    res = logic.run_analysis(get_provider().get_ohlcv(asset), period_key, json.loads(buy_json), json.loads(sell_json),
                             cash, risk, sl, tp, com, slip, ASSET_LABELS[asset], c_start, c_end)
    res["extra"] = logic.summarize(res, sl, slip)
    return res


@st.cache_data(ttl=3600, show_spinner="Calcul de la projection…")
def projection(asset):
    return logic.projection_view(get_provider().get_ohlcv(asset), ASSET_LABELS[asset])


def money(v, d=2):
    return f"{v:,.{d}f}".replace(",", " ")


def signed(v, d=2, suffix=""):
    return f"{'+' if v >= 0 else '−'}{money(abs(v), d)}{suffix}"


def rule_builder(prefix: str, defaults: list) -> dict:
    n = st.number_input("Nombre de conditions", 1, 5, len(defaults), key=f"{prefix}_n")
    combo = st.radio("Logique", ["AND", "OR"], horizontal=True, key=f"{prefix}_logic",
                     format_func=lambda x: "ET" if x == "AND" else "OU")
    names = list(logic.INDICATOR_CHOICES)
    conditions = []
    for i in range(int(n)):
        d = defaults[i] if i < len(defaults) else ("Prix", ">", "Valeur", 0.0, "SMA 200")
        left = st.selectbox("Indicateur", names, index=names.index(d[0]), key=f"{prefix}_l{i}")
        c1, c2 = st.columns([1, 2])
        op = c1.selectbox("Op.", logic.OPERATORS, index=logic.OPERATORS.index(d[1]), key=f"{prefix}_o{i}")
        mode = c2.radio("Comparer à", ["Valeur", "Indicateur"], index=0 if d[2] == "Valeur" else 1,
                        key=f"{prefix}_m{i}", horizontal=True)
        if mode == "Valeur":
            conditions.append(logic.make_condition(left, op, mode, value=st.number_input("Seuil", value=float(d[3]), key=f"{prefix}_v{i}")))
        else:
            right = st.selectbox("Indicateur de comparaison", names, index=names.index(d[4]), key=f"{prefix}_r{i}")
            conditions.append(logic.make_condition(left, op, mode, right_label=right))
        if i < int(n) - 1:
            st.caption("— ET —" if combo == "AND" else "— OU —")
    return logic.make_rule(combo, conditions)


def rule_text(rule: dict) -> str:
    sep = " ET " if rule["logic"] == "AND" else " OU "
    parts = []
    for c in rule["conditions"]:
        right = c["right"] if isinstance(c["right"], (int, float)) else _spec_name(c["right"])
        parts.append(f"{_spec_name(c['left'])} {c['operator']} {right}")
    return sep.join(parts)


def _spec_name(spec: dict) -> str:
    for label, s in logic.INDICATOR_CHOICES.items():
        if s == spec:
            return label
    return spec["name"]


def show_chart(payload: dict, height_main: int, height_rsi: int = 130):
    components.html(tv_chart.build_chart_html(payload, height_main=height_main, height_rsi=height_rsi),
                    height=logic.chart_height(payload, height_main, height_rsi), scrolling=False)


# ------------------------------------------------------------------ données réelles
provider = get_provider()
markets, unavailable = {}, {}
for key in ASSET_LABELS:
    try:
        df = provider.get_ohlcv(key)
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        markets[key] = {"last": last, "chg": (last / prev - 1) * 100, **provider.info(key)}
    except DataUnavailable as exc:
        unavailable[key] = str(exc)
if not markets:
    st.error("Aucune donnée de marché disponible pour le moment. Réessayez dans quelques minutes.")
    st.stop()

# ------------------------------------------------------------------ panneau de gauche : liste de suivi + stratégie
with st.sidebar:
    st.markdown("### 📈 StrategyLab")
    st.caption("Testez votre stratégie sur l'historique du marché")
    st.markdown("**Liste de suivi**")
    asset = st.radio("Actif", list(markets), label_visibility="collapsed",
                     format_func=lambda k: f"{ASSET_LABELS[k]}   {money(markets[k]['last'])}   ({markets[k]['chg']:+.2f} %)")
    for k, reason in unavailable.items():
        st.caption(f"{ASSET_LABELS[k]} : indisponible. {reason}")
    st.markdown("**Stratégie**")
    tab_buy, tab_sell = st.tabs(["Entrée Achat", "Entrée Vente"])
    with tab_buy:
        buy_rule = rule_builder("buy", DEFAULT_BUY)
    with tab_sell:
        sell_rule = rule_builder("sell", DEFAULT_SELL)
    st.markdown("**Capital & risque**")
    a1, a2 = st.columns(2)
    cash = a1.number_input("Capital ($)", value=DEFAULT_INITIAL_CASH, min_value=100.0, step=100.0)
    risk_pct = a2.number_input("Risque / trade (%)", value=DEFAULT_RISK_PCT * 100, min_value=0.01, max_value=100.0)
    b1, b2 = st.columns(2)
    sl_pct = b1.number_input("Stop loss (%)", value=DEFAULT_STOP_LOSS_PCT * 100, min_value=0.05, max_value=99.0)
    tp_pct = b2.number_input("Take profit (%)", value=DEFAULT_TAKE_PROFIT_PCT * 100, min_value=0.05, max_value=500.0)
    c1, c2 = st.columns(2)
    commission = c1.number_input("Commission (%)", value=DEFAULT_COMMISSION_RATE * 100, min_value=0.0, max_value=5.0, step=0.01)
    slippage = c2.number_input("Slippage (%)", value=DEFAULT_SLIPPAGE_RATE * 100, min_value=0.0, max_value=5.0, step=0.01)
    st.caption("Taille de position calculée selon le risque (capital × risque ÷ distance du stop). "
               "Les résultats passés ne garantissent pas les performances futures.")

# ------------------------------------------------------------------ en-tête : actif + périodes
info = markets[asset]
st.markdown(f"<span class='sl-title'>{ASSET_LABELS[asset]}</span> <span class='sl-sub'>· 1J · données jusqu'au "
            f"{info.get('last_date')} · {info.get('source')} · actualisation automatique</span>", unsafe_allow_html=True)
period_key = st.radio("Période", PERIOD_ORDER, index=PERIOD_ORDER.index("5Y"), horizontal=True, label_visibility="collapsed",
                      format_func=lambda k: PERIOD_SHORT[k])
c_start = c_end = None
if period_key == "CUSTOM":
    last_day = pd.Timestamp(info["last_date"])
    d1, d2, _ = st.columns([1, 1, 4])
    c_start = d1.date_input("Début", value=(last_day - pd.Timedelta(days=365)).date()).isoformat()
    c_end = d2.date_input("Fin", value=last_day.date()).isoformat()

# ------------------------------------------------------------------ analyse (Python) et affichage
try:
    res = analyse(asset, period_key, c_start, c_end, cash, risk_pct / 100, sl_pct / 100, tp_pct / 100,
                  commission / 100, slippage / 100, json.dumps(buy_rule), json.dumps(sell_rule))
except (ValueError, DataUnavailable) as exc:
    st.error(str(exc))
    st.stop()

rep, extra = res["report"], res["extra"]
if not rep["reliable_sample"]:
    st.warning(f"Échantillon faible ({rep['n_trades']} trade{'s' if rep['n_trades'] > 1 else ''}) : à interpréter avec prudence, "
               "trop peu de trades pour une lecture statistique fiable.")
if info.get("stale_error"):
    st.warning(f"Mise à jour des données impossible ({info['stale_error']}) : dernière copie connue utilisée.")
if info.get("ohlc_approx"):
    st.info("Cet actif ne fournit que la clôture du jour : bougies reconstruites (pas de vraies mèches), indicateurs de volume désactivés.")

show_chart(res["chart_payload"], height_main=470)

t_over, t_perf, t_trades, t_props, t_proj = st.tabs(["Aperçu", "Résumé de la performance", "Liste des trades", "Propriétés", "Projection"])
pnl = rep["final_equity"] - rep["initial_cash"]
pf = "∞" if rep["profit_factor"] == float("inf") else ("—" if rep["profit_factor"] is None else f"{rep['profit_factor']:.2f}")
with t_over:
    k = st.columns(5)
    k[0].metric("P&L total", signed(pnl, 2, " $"), delta=f"{rep['return_pct']:+.2f} %")
    k[1].metric("Drawdown maximal", f"{rep['max_drawdown_pct']:.2f} %")
    k[2].metric("Nombre de trades", rep["n_trades"], delta=f"{rep['n_wins']} gagnants · {rep['n_losses']} perdants", delta_color="off")
    k[3].metric("Trades gagnants", f"{rep['win_rate_pct']:.1f} %" if rep["n_trades"] else "—")
    k[4].metric("Profit factor", pf)
    st.area_chart(res["equity"].set_index("timestamp")["equity"], height=220)
with t_perf:
    rows = [
        ("Capital initial", f"{money(rep['initial_cash'])} $"), ("Capital final", f"{money(rep['final_equity'])} $"),
        ("P&L total", signed(pnl, 2, " $")), ("Rendement", signed(rep["return_pct"], 2, " %")),
        ("Drawdown maximal", f"{rep['max_drawdown_pct']:.2f} %"), ("Nombre de trades", str(rep["n_trades"])),
        ("Trades gagnants", str(rep["n_wins"])), ("Trades perdants", str(rep["n_losses"])),
        ("Taux de réussite", f"{rep['win_rate_pct']:.2f} %" if rep["n_trades"] else "—"),
        ("Gain moyen par trade", signed(rep["avg_win_dollars"], 2, " $") if rep["n_wins"] else "—"),
        ("Perte moyenne par trade", signed(rep["avg_loss_dollars"], 2, " $") if rep["n_losses"] else "—"),
        ("Espérance par trade", signed(rep["expectancy_dollars"], 2, " $") if rep["n_trades"] else "—"),
        ("Profit factor", pf),
        ("Ratio de Sharpe (annualisé, 252 séances)", "—" if extra["sharpe_ratio"] is None else f"{extra['sharpe_ratio']:.2f}"),
        ("Durée moyenne d'un trade (séances)", f"{rep['avg_trade_duration_bars']:.1f}" if rep["n_trades"] else "—"),
        ("Frais de transaction", f"{money(rep['total_fees_dollars'])} $"),
        ("Slippage estimé", f"{money(extra['slippage_estimated_dollars'])} $"),
    ] + [(f"Sorties : {REASONS.get(r, r)}", str(n)) for r, n in extra["exit_reasons"].items()]
    st.table(pd.DataFrame(rows, columns=["Indicateur", "Valeur"]).set_index("Indicateur"))
with t_trades:
    if not extra["trade_rows"]:
        st.write("Aucun trade sur cette configuration.")
    else:
        tr = pd.DataFrame(extra["trade_rows"]).rename(columns={
            "entry": "Entrée", "exit": "Sortie", "entry_price": "Prix entrée", "exit_price": "Prix sortie", "quantity": "Quantité",
            "pnl": "Résultat ($)", "pnl_pct": "Résultat (%)", "r": "R", "reason": "Raison"})
        tr["Raison"] = tr["Raison"].map(lambda r: REASONS.get(r, r))
        st.dataframe(tr)
        st.download_button("Exporter (CSV)", tr.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name="strategylab_trades.csv", mime="text/csv")
with t_props:
    props = [("Actif", ASSET_LABELS[asset]), ("Période", rep["period"]), ("Capital initial", f"{money(cash)} $"),
             ("Risque par trade", f"{risk_pct:.2f} %"), ("Stop loss", f"{sl_pct:.2f} %"), ("Take profit", f"{tp_pct:.2f} %"),
             ("Commission", f"{commission:.2f} %"), ("Slippage", f"{slippage:.2f} %"),
             ("Règle d'achat", rule_text(buy_rule)), ("Règle de vente", rule_text(sell_rule)),
             ("Source des données", str(info.get("source"))), ("Dernière date", str(info.get("last_date")))]
    st.table(pd.DataFrame(props, columns=["Paramètre", "Valeur"]).set_index("Paramètre"))
with t_proj:
    try:
        view = projection(asset)
        st.caption("Plage de probabilité issue de la volatilité historique : "
                   f"{view['n_paths']} trajectoires simulées, même dispersion que par le passé, aucune tendance supposée. "
                   "Ce n'est PAS une prédiction. Bougies pleines = historique réel ; bougies orange = plage simulée (une par mois).")
        show_chart(view["payload"], height_main=360)
        st.table(pd.DataFrame(view["table"]).rename(columns={
            "echeance": "Échéance", "date": "Date", "p10": "10e percentile", "mediane": "Médiane", "p90": "90e percentile"}).set_index("Échéance"))
    except ValueError as exc:
        st.info(str(exc))

st.caption(rep["disclaimer"])
