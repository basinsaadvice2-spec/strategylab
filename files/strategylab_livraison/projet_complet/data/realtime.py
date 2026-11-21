"""
Architecture pour des données qui se mettent à jour en continu, sans
changer une seule ligne de indicators/strategy/backtest — c'est tout
l'intérêt d'avoir isolé DataProvider dès la V1.

Deux façons de "brancher du temps réel" ici, du plus simple au plus
avancé :

1. import_new_bars() — la plus simple, ne nécessite AUCUNE clé API dès
   maintenant : tu déposes régulièrement (à la main, ou via un cron/tâche
   planifiée) un CSV avec les nouvelles barres, et cette fonction les
   fusionne dans le fichier existant en évitant les doublons. C'est la
   bonne option pour démarrer sans dépendre d'un service tiers payant.

2. RealtimeDataProvider — l'abstraction complète pour un vrai flux live
   (API de courtier, WebSocket, etc.). Il ne fait rien tant qu'on ne lui
   donne pas une fonction `fetch_fn` qui sait interroger la vraie source
   (ça, c'est la partie qui nécessite ton aide pour choisir/connecter un
   fournisseur de données réel — API key, format de réponse, etc.). Une
   fois `fetch_fn` fourni, TOUT le reste du logiciel (indicateurs,
   stratégie, backtest, rapport) fonctionne sans aucune modification.
"""
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from data.provider import DataProvider
from data.loader import load_ohlcv, validate_ohlcv, REQUIRED

logger = logging.getLogger(__name__)


def import_new_bars(asset_csv_path: str | Path, new_bars_csv_path: str | Path) -> int:
    """Fusionne `new_bars_csv_path` dans `asset_csv_path` (même format
    OHLCV que d'habitude). Les barres dont le timestamp existe déjà sont
    ignorées (pas de doublon, pas d'écrasement silencieux d'une donnée
    déjà validée). Retourne le nombre de nouvelles barres ajoutées.

    Usage typique : exporter un CSV depuis n'importe quelle source (le
    site d'un courtier, une app), puis lancer cette fonction pour que
    StrategyLab en tienne compte — aucune API requise.
    """
    asset_csv_path = Path(asset_csv_path)
    existing = load_ohlcv(asset_csv_path) if asset_csv_path.exists() else pd.DataFrame(
        columns=REQUIRED
    )
    new_bars = load_ohlcv(new_bars_csv_path)

    before = len(existing)
    combined = pd.concat([existing, new_bars], ignore_index=True)
    combined = combined.sort_values("timestamp").drop_duplicates(
        subset="timestamp", keep="last"
    ).reset_index(drop=True)

    combined.to_csv(asset_csv_path, index=False)
    added = len(combined) - before
    logger.info("%d nouvelle(s) barre(s) ajoutée(s) à %s (total: %d).",
                added, asset_csv_path, len(combined))
    return added


class RealtimeDataProvider(DataProvider):
    """DataProvider qui rafraîchit son cache toutes les `refresh_seconds`
    en appelant `fetch_fn(symbol) -> DataFrame OHLCV`. `fetch_fn` est la
    seule pièce manquante pour un vrai flux live : c'est la fonction qui
    sait parler à la vraie source de données (API broker, WebSocket,
    base de données déjà alimentée ailleurs, etc.).

    Tant que `fetch_fn` n'est pas fourni, ce provider lève une erreur
    claire plutôt que d'inventer des données — jamais de faux silence.
    """

    def __init__(self, fetch_fn: Optional[Callable[[str], pd.DataFrame]] = None,
                 refresh_seconds: int = 60):
        if refresh_seconds < 1:
            raise ValueError("refresh_seconds doit être >= 1")
        self.fetch_fn = fetch_fn
        self.refresh_seconds = refresh_seconds
        self._cache: dict[str, pd.DataFrame] = {}
        self._last_fetch: dict[str, float] = {}

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        if self.fetch_fn is None:
            raise NotImplementedError(
                "Aucune source de données live connectée. Il faut fournir "
                "fetch_fn (fonction qui interroge la vraie source — API "
                "broker, base de données, etc.) pour activer le temps réel. "
                "En attendant, utilise CSVDataProvider ou import_new_bars()."
            )

        symbol = symbol.upper()
        now = time.time()
        is_stale = (
            symbol not in self._cache
            or now - self._last_fetch.get(symbol, 0) > self.refresh_seconds
        )
        if is_stale:
            fresh = self.fetch_fn(symbol)
            # les données reçues du live passent par les MÊMES contrôles
            # qualité que n'importe quel CSV (pas de traitement de faveur
            # pour une source "temps réel" — une donnée fausse reste fausse
            # même si elle est fraîche).
            fresh = _validate_ohlcv_frame(fresh)
            self._cache[symbol] = fresh
            self._last_fetch[symbol] = now
            logger.info("Données rafraîchies pour %s (%d barres).", symbol, len(fresh))

        return self._cache[symbol].copy()


def _validate_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Mêmes contrôles que pour un fichier CSV (data/loader.validate_ohlcv)."""
    return validate_ohlcv(df)
