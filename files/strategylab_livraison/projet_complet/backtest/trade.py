from dataclasses import dataclass


@dataclass
class Trade:
    entry_time: object
    exit_time: object
    entry_price: float
    exit_price: float
    quantity: float
    fees: float
    pnl_dollars: float
    pnl_pct: float
    exit_reason: str  # "SL" | "TP" | "SIGNAL" | "END_OF_DATA"
    duration_bars: int
    sltp_ambiguous: bool = False
