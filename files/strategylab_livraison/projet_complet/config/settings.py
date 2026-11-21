"""
Paramètres par défaut de StrategyLab.
Aucun secret ici, aucune clé API — voir CLAUDE_STRATEGYLAB_PROMPT.md § Sécurité.
"""

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


# --- Firebase (base de données alimentée toutes les heures par la fonction firebase/functions/index.js) ---
# La clé web Firebase n'est PAS un secret : elle identifie le projet côté client. La protection vient des
# règles Firestore (lecture seule, aucune écriture possible depuis l'extérieur). Surchargeable par les
# variables / secrets FIREBASE_PROJECT_ID et FIREBASE_API_KEY.
FIREBASE_PROJECT_ID = "tradermaker-67ddf"
FIREBASE_WEB_API_KEY = "AIzaSyDmehoI2bRPJgRhjneSlzp0ASeA3XlTAlw"
