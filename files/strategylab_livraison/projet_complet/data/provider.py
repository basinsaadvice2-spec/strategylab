"""
Couche DataProvider: le moteur de backtest ne sait jamais d'où viennent les
données. En V1 on ne lit que du CSV/Parquet local (pas de cloud, pas d'API
payante), mais une future source (API broker, base de données) n'implique
qu'un nouveau provider respectant cette interface.
"""
from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd

from data.loader import load_ohlcv


class DataProvider(ABC):
    @abstractmethod
    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        """Retourne les données OHLCV complètes et validées pour ce symbole."""
        raise NotImplementedError


class CSVDataProvider(DataProvider):
    """Charge chaque symbole depuis un chemin CSV/Parquet local configuré
    dans config.settings.ASSETS."""

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
