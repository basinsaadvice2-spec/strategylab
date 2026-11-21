"""
Chargement + validation/nettoyage des données OHLCV.
Reprend et généralise les corrections faites lors de l'audit du bot V0.2 :
détection des valeurs manquantes, cohérence OHLC, doublons de timestamp
signalés (pas juste supprimés en silence).
"""
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
    """Contrôles qualité communs à TOUTES les sources (fichier, API, base) :
    une donnée fausse reste fausse même si elle est fraîche. Renvoie un
    DataFrame propre (trié, sans doublon) ou lève ValueError."""
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
