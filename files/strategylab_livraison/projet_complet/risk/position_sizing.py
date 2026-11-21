"""
Position sizing basé sur le risque, comme demandé dans le cahier des
charges: "10 000 $ × 2 % = 200 $ de risque théorique par trade si le stop
est exécuté."

quantité = (capital × risque%) / (prix d'entrée × stop_loss%)
"""


def size_position(cash: float, entry_price: float, risk_pct: float,
                   stop_loss_pct: float) -> tuple[float, float]:
    """Retourne (quantité, risque_théorique_dollars).

    La quantité est ensuite plafonnée par le cash réellement disponible côté
    Portfolio (voir portfolio/portfolio.py) — ce module ne connaît que la
    règle de risque, pas l'état du compte.
    """
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
