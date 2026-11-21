"""
Registre d'indicateurs: transforme une spec déclarative (dict) en série
pandas nommée, avec cache pour ne jamais recalculer deux fois le même
indicateur dans une même stratégie. Ajouter un nouvel indicateur = ajouter
une entrée dans _BUILDERS, rien d'autre à toucher.

V1.1: passage de 8 à 26 indicateurs (tendance, momentum, volatilité,
volume) — la liste complète est dans list_available_indicators().
"""
import pandas as pd

from indicators import trend, momentum, volatility, volume as volume_mod, price as price_mod


def label(spec: dict) -> str:
    """Nom de colonne stable et lisible pour une spec d'indicateur."""
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
    """Utilisé par l'UI (Streamlit) pour peupler les listes déroulantes."""
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
            if name in _VOLUME_BASED and "volume" in self.df.columns \
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
