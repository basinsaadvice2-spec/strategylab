"""
Projection STATISTIQUE (Monte Carlo) — une plage de probabilité, jamais une
prédiction. À partir de la dispersion historique des variations journalières,
on simule des milliers de trajectoires possibles et on lit des percentiles.

Hypothèses (affichées dans l'interface) :
- les variations futures suivent la même dispersion que le passé (peut être faux) ;
- dérive nulle par défaut : le modèle ne prend PAS parti sur la direction
  (hausse/baisse). Sa médiane reste donc proche du dernier prix.
Graine fixe : deux exécutions donnent exactement le même résultat.
"""
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
    """`df` : colonnes timestamp, close (trié). `lookback_bars` limite la
    fenêtre d'estimation de la volatilité (par défaut ~10 ans de séances)."""
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
