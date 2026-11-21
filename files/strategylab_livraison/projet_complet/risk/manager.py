from dataclasses import dataclass


@dataclass
class RiskParams:
    risk_pct: float
    stop_loss_pct: float
    take_profit_pct: float

    def __post_init__(self):
        if not (0 < self.risk_pct <= 1):
            raise ValueError("risk_pct doit être dans ]0, 1].")
        if not (0 < self.stop_loss_pct < 1):
            raise ValueError("stop_loss_pct doit être dans ]0, 1[.")
        if not (0 < self.take_profit_pct < 5):
            raise ValueError("take_profit_pct doit être dans ]0, 5[.")

    def stop_loss_price(self, entry_price: float) -> float:
        return entry_price * (1 - self.stop_loss_pct)

    def take_profit_price(self, entry_price: float) -> float:
        return entry_price * (1 + self.take_profit_pct)
