"""
Résolution des périodes standards demandées par le client (1, 3, 5, 10 ans,
quelques fenêtres courtes utiles, et personnalisée) + découpage chronologique
développement / validation / hors-échantillon.

Le choix explicite de périodes "courantes" plutôt que n'importe quelle
fenêtre arbitraire vient d'une demande directe du client: il veut pouvoir
être sûr de la lecture du signal sur des horizons qu'on utilise
habituellement en pratique, pas fabriquer une fenêtre sur mesure qui
"marche" par hasard.
"""
from datetime import timedelta
import pandas as pd

from config.settings import STANDARD_PERIODS


def resolve_period(df: pd.DataFrame, period_key: str,
                    custom_start=None, custom_end=None) -> pd.DataFrame:
    """Filtre `df` (trié par timestamp) sur la période demandée.

    period_key: une clé de config.settings.STANDARD_PERIODS, ex. "5Y", "3D",
    ou "CUSTOM" avec custom_start/custom_end fournis (str ou Timestamp,
    interprétés en UTC).
    """
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
    """Découpe `df` en trois blocs CONSÉCUTIFS dans le temps (jamais mélangés
    au hasard, l'ordre chronologique est la garantie principale contre le
    data leakage): développement, validation, hors-échantillon.

    Le jeu hors-échantillon ne doit jamais servir à ajuster les paramètres
    de la stratégie — voir CLAUDE_STRATEGYLAB_PROMPT.md § Validation.
    """
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
