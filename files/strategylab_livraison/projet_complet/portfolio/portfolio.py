from dataclasses import dataclass


@dataclass
class Position:
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_timestamp: object


class Portfolio:
    """Long uniquement en V1 (le cahier des charges ne demande pas le
    short). Une seule position ouverte à la fois."""

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
        """Ferme la position au prix donné, crédite le cash, renvoie le
        produit de la vente (avant frais — les frais sont appliqués par le
        backtest engine, qui connaît le taux de commission)."""
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
