"""
Moteur de backtest. Règle absolue (cahier des charges): aucune décision à T
ne peut utiliser une information de T+1 ou après.

Comment c'est garanti ici:
- Les indicateurs et signaux (buy_signal/sell_signal) sont calculés à la
  clôture de la barre T avec des données connues à T.
- L'EXÉCUTION d'un signal a toujours lieu à l'OUVERTURE de la barre T+1,
  jamais sur la clôture de T elle-même.
- Une fois en position, le SL/TP est vérifié barre par barre sur les
  high/low réellement observés, jamais anticipé.
"""
import pandas as pd

from portfolio.portfolio import Portfolio
from risk.manager import RiskParams
from risk.position_sizing import size_position
from backtest.trade import Trade


class BacktestEngine:
    def __init__(self, initial_cash: float, risk: RiskParams,
                 commission_rate: float, slippage_rate: float,
                 sltp_ambiguity_policy: str = "stop_first"):
        if commission_rate < 0:
            raise ValueError("commission_rate ne peut pas être négatif.")
        if slippage_rate < 0:
            raise ValueError("slippage_rate ne peut pas être négatif.")
        if sltp_ambiguity_policy not in ("stop_first", "tp_first", "flag_only"):
            raise ValueError(
                "sltp_ambiguity_policy doit être stop_first, tp_first ou flag_only."
            )

        self.initial_cash = initial_cash
        self.risk = risk
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.sltp_ambiguity_policy = sltp_ambiguity_policy

    def run(self, df: pd.DataFrame):
        required = {"timestamp", "open", "high", "low", "close", "buy_signal", "sell_signal"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Colonnes manquantes pour le backtest: {missing}")

        portfolio = Portfolio(self.initial_cash)
        trades: list[Trade] = []
        equity_rows = []

        pending_buy = False
        pending_sell_signal = False
        entry_bar_index = None

        n = len(df)
        for i in range(n):
            row = df.iloc[i]

            # --- 1. Exécuter les signaux décidés à la barre précédente ---
            if pending_buy and not portfolio.in_position:
                entry_price = row["open"] * (1 + self.slippage_rate)
                try:
                    qty, _risk_dollars = size_position(
                        portfolio.cash, entry_price,
                        self.risk.risk_pct, self.risk.stop_loss_pct,
                    )
                    max_affordable = portfolio.cash / (entry_price * (1 + self.commission_rate))
                    qty = min(qty, max_affordable)
                    if qty > 0:
                        fee = qty * entry_price * self.commission_rate
                        if qty * entry_price + fee <= portfolio.cash:
                            sl = self.risk.stop_loss_price(entry_price)
                            tp = self.risk.take_profit_price(entry_price)
                            portfolio.cash -= fee  # frais d'entrée prélevés séparément
                            portfolio.open_position(qty, entry_price, sl, tp, row["timestamp"])
                            entry_bar_index = i
                            self._entry_fee = fee
                except ValueError:
                    pass  # cash insuffisant ou paramètres invalides -> pas de trade
            pending_buy = False

            if pending_sell_signal and portfolio.in_position:
                exit_price = row["open"] * (1 - self.slippage_rate)
                self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                   reason="SIGNAL", entry_bar_index=entry_bar_index,
                                   current_bar_index=i)
                entry_bar_index = None
            pending_sell_signal = False

            # --- 2. Vérifier SL/TP intrabar si en position ---
            if portfolio.in_position:
                pos = portfolio.position
                hit_sl = row["low"] <= pos.stop_loss
                hit_tp = row["high"] >= pos.take_profit
                if hit_sl and hit_tp:
                    ambiguous = True
                    if self.sltp_ambiguity_policy == "tp_first":
                        exit_price = pos.take_profit
                        reason = "TP"
                    else:
                        # "stop_first" par défaut (prudent) et "flag_only"
                        # utilisent aussi le stop comme hypothèse par défaut,
                        # mais flag_only marque explicitement l'ambiguïté
                        # pour revue manuelle.
                        exit_price = pos.stop_loss
                        reason = "SL"
                    exit_price *= (1 - self.slippage_rate)
                    self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                       reason=reason, entry_bar_index=entry_bar_index,
                                       current_bar_index=i, ambiguous=ambiguous)
                    entry_bar_index = None
                elif hit_sl:
                    exit_price = pos.stop_loss * (1 - self.slippage_rate)
                    self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                       reason="SL", entry_bar_index=entry_bar_index,
                                       current_bar_index=i)
                    entry_bar_index = None
                elif hit_tp:
                    exit_price = pos.take_profit * (1 - self.slippage_rate)
                    self._close_trade(portfolio, trades, exit_price, row["timestamp"],
                                       reason="TP", entry_bar_index=entry_bar_index,
                                       current_bar_index=i)
                    entry_bar_index = None

            # --- 3. Enregistrer l'équité mark-to-market à la clôture ---
            equity_rows.append({
                "timestamp": row["timestamp"],
                "equity": portfolio.equity(row["close"]),
            })

            # --- 4. Décider les actions pour la PROCHAINE barre (pas d'exécution ici) ---
            if not portfolio.in_position and bool(row["buy_signal"]):
                pending_buy = True
            if portfolio.in_position and bool(row["sell_signal"]):
                pending_sell_signal = True

        # Fin des données: si une position reste ouverte, on la clôture au
        # dernier prix connu pour ne pas fausser les statistiques de trades,
        # avec une raison explicite.
        if portfolio.in_position:
            last_row = df.iloc[-1]
            self._close_trade(portfolio, trades, last_row["close"], last_row["timestamp"],
                               reason="END_OF_DATA", entry_bar_index=entry_bar_index,
                               current_bar_index=n - 1)
            equity_rows[-1]["equity"] = portfolio.equity(last_row["close"])

        trades_df = pd.DataFrame([t.__dict__ for t in trades])
        equity_df = pd.DataFrame(equity_rows)
        return trades_df, equity_df

    def _close_trade(self, portfolio: Portfolio, trades: list, exit_price: float,
                      exit_time, reason: str, entry_bar_index: int,
                      current_bar_index: int, ambiguous: bool = False):
        pos = portfolio.position
        entry_fee = getattr(self, "_entry_fee", 0.0)
        exit_fee = pos.quantity * exit_price * self.commission_rate
        proceeds = portfolio.close_position(exit_price)
        portfolio.cash -= exit_fee

        entry_cost = pos.quantity * pos.entry_price
        total_fees = entry_fee + exit_fee
        pnl_dollars = (proceeds - exit_fee) - (entry_cost + entry_fee)
        pnl_pct = (pnl_dollars / (entry_cost + entry_fee)) * 100 if entry_cost > 0 else 0.0
        duration = (current_bar_index - entry_bar_index) if entry_bar_index is not None else 0

        trades.append(Trade(
            entry_time=pos.entry_timestamp,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            fees=total_fees,
            pnl_dollars=pnl_dollars,
            pnl_pct=pnl_pct,
            exit_reason=reason,
            duration_bars=duration,
            sltp_ambiguous=ambiguous,
        ))
        self._entry_fee = 0.0
