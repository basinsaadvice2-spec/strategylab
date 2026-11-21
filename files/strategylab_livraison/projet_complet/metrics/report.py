import numpy as np
import pandas as pd

from config.settings import MIN_TRADES_FOR_RELIABLE_STATS


def build_report(trades: pd.DataFrame, equity: pd.DataFrame, initial_cash: float,
                  asset: str, period_label: str, commission_rate: float,
                  slippage_rate: float) -> dict:
    if initial_cash <= 0:
        raise ValueError("initial_cash doit être strictement positif.")

    final_equity = float(equity["equity"].iloc[-1]) if not equity.empty else initial_cash
    return_pct = (final_equity / initial_cash - 1) * 100

    if equity.empty:
        max_dd = 0.0
    else:
        peak = equity["equity"].cummax()
        max_dd = float(((equity["equity"] / peak - 1) * 100).min())

    n_trades = len(trades)
    if n_trades > 0:
        wins = trades[trades["pnl_dollars"] > 0]
        losses = trades[trades["pnl_dollars"] < 0]
        win_rate = 100 * len(wins) / n_trades
        avg_win = float(wins["pnl_dollars"].mean()) if len(wins) else 0.0
        avg_loss = float(losses["pnl_dollars"].mean()) if len(losses) else 0.0
        gross_profit = float(wins["pnl_dollars"].sum())
        gross_loss = abs(float(losses["pnl_dollars"].sum()))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else None
        )
        expectancy = float(trades["pnl_dollars"].mean())
        total_fees = float(trades["fees"].sum())
        avg_duration_bars = float(trades["duration_bars"].mean())
        n_ambiguous = int(trades["sltp_ambiguous"].sum())
    else:
        win_rate = avg_win = avg_loss = expectancy = total_fees = avg_duration_bars = 0.0
        profit_factor = None
        n_ambiguous = 0

    report = {
        "asset": asset,
        "period": period_label,
        "initial_cash": initial_cash,
        "final_equity": final_equity,
        "return_pct": return_pct,
        "max_drawdown_pct": max_dd,
        "n_trades": n_trades,
        "n_wins": int((trades["pnl_dollars"] > 0).sum()) if n_trades else 0,
        "n_losses": int((trades["pnl_dollars"] < 0).sum()) if n_trades else 0,
        "win_rate_pct": win_rate,
        "avg_win_dollars": avg_win,
        "avg_loss_dollars": avg_loss,
        "profit_factor": profit_factor,
        "expectancy_dollars": expectancy,
        "total_fees_dollars": total_fees,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
        "avg_trade_duration_bars": avg_duration_bars,
        "sltp_ambiguous_trades": n_ambiguous,
        "reliable_sample": n_trades >= MIN_TRADES_FOR_RELIABLE_STATS,
        "disclaimer": (
            "Résultats descriptifs sur données historiques. Ceci ne "
            "constitue en aucun cas une garantie de performance future."
        ),
    }
    return report
