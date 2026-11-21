"""
Génère des séries OHLCV SYNTHÉTIQUES (pas des vraies données de marché) pour
Gold et Oil, utilisées pour les démos et les tests. À remplacer par de
vraies données historiques (CSV/Parquet) via config.settings.ASSETS dès
qu'elles sont disponibles.
"""
import numpy as np
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).parent


def _generate(start_price: float, years: int, annual_vol: float,
              annual_drift: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_days = years * 365
    ts = pd.date_range("2015-01-01", periods=n_days, freq="D", tz="UTC")

    daily_vol = annual_vol / np.sqrt(365)
    daily_drift = annual_drift / 365
    returns = rng.normal(daily_drift, daily_vol, n_days)
    close = start_price * np.cumprod(1 + returns)
    close = np.maximum(close, start_price * 0.1)

    # un peu de bruit intra-journalier pour générer high/low/open cohérents
    intraday = rng.uniform(0.002, 0.012, n_days)
    open_ = close * (1 + rng.normal(0, 0.002, n_days))
    open_ = np.maximum(open_, 0.01)
    high = np.maximum(open_, close) * (1 + intraday)
    low = np.minimum(open_, close) * (1 - intraday)
    volume = rng.integers(1000, 50000, n_days)

    return pd.DataFrame({
        "timestamp": ts, "open": open_, "high": high, "low": low,
        "close": close, "volume": volume,
    })


def main():
    gold = _generate(start_price=1200, years=10, annual_vol=0.14,
                      annual_drift=0.06, seed=7)
    oil = _generate(start_price=55, years=10, annual_vol=0.35,
                     annual_drift=0.02, seed=13)
    gold.to_csv(OUT_DIR / "gold_synthetic.csv", index=False)
    oil.to_csv(OUT_DIR / "oil_synthetic.csv", index=False)
    print(f"gold: {len(gold)} lignes, oil: {len(oil)} lignes")


if __name__ == "__main__":
    main()
