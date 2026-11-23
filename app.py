import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import date, timedelta

st.set_page_config(page_title="StrategyLab", page_icon="📈", layout="wide")

# ----------------------------- Data ---------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def load_market_data(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Download daily OHLCV data. end_date is inclusive in the UI."""
    raw = yf.download(
        symbol,
        start=start_date,
        end=end_date + timedelta(days=1),
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    required = ["Open", "High", "Low", "Close"]
    if not set(required).issubset(raw.columns):
        return pd.DataFrame()
    data = raw[required].copy()
    for col in required:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    data = data[(data["High"] >= data["Low"]) & (data["Close"] > 0)]
    data.index = pd.to_datetime(data.index).tz_localize(None)
    return data.sort_index()


# -------------------------- Indicators ------------------------------
def add_indicators(data: pd.DataFrame, strategy: str, p1: int, p2: int) -> pd.DataFrame:
    out = data.copy()
    close = out["Close"]
    if strategy == "Moving average crossover":
        out["Indicator_1"] = close.rolling(p1, min_periods=p1).mean()
        out["Indicator_2"] = close.rolling(p2, min_periods=p2).mean()
        out["Signal"] = (out["Indicator_1"] > out["Indicator_2"]).astype(int)
        out.loc[out["Indicator_1"].isna() | out["Indicator_2"].isna(), "Signal"] = 0
    elif strategy == "RSI":
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / p1, adjust=False, min_periods=p1).mean()
        avg_loss = loss.ewm(alpha=1 / p1, adjust=False, min_periods=p1).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
        rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0)
        out["Indicator_1"] = rsi
        # Long-only example: enter after RSI crosses up through oversold;
        # exit after it crosses down through overbought.
        enter = (rsi.shift(1) <= p2) & (rsi > p2)
        leave = (rsi.shift(1) >= 100 - p2) & (rsi < 100 - p2)
        state = 0
        signals = []
        for e, x in zip(enter.fillna(False), leave.fillna(False)):
            if state == 0 and e:
                state = 1
            elif state == 1 and x:
                state = 0
            signals.append(state)
        out["Signal"] = signals
        out.loc[rsi.isna(), "Signal"] = 0
    elif strategy == "MACD":
        fast = close.ewm(span=p1, adjust=False, min_periods=p1).mean()
        slow = close.ewm(span=p2, adjust=False, min_periods=p2).mean()
        macd = fast - slow
        signal_line = macd.ewm(span=9, adjust=False, min_periods=9).mean()
        out["Indicator_1"] = macd
        out["Indicator_2"] = signal_line
        out["Signal"] = (macd > signal_line).astype(int)
        out.loc[signal_line.isna(), "Signal"] = 0
    else:  # Donchian channel breakout
        upper = out["High"].rolling(p1, min_periods=p1).max().shift(1)
        lower = out["Low"].rolling(p1, min_periods=p1).min().shift(1)
        out["Indicator_1"] = upper
        out["Indicator_2"] = lower
        enter = close > upper
        leave = close < lower
        state = 0
        signals = []
        for e, x in zip(enter.fillna(False), leave.fillna(False)):
            if state == 0 and e:
                state = 1
            elif state == 1 and x:
                state = 0
            signals.append(state)
        out["Signal"] = signals
        out.loc[upper.isna() | lower.isna(), "Signal"] = 0
    return out


# -------------------------- Backtest --------------------------------
def run_backtest(data: pd.DataFrame, initial_capital: float, fee_rate: float,
                 stop_pct: float, target_pct: float):
    """
    Long-only, fully invested, one position at a time.
    Signal at close t is executed at open t+1.
    Stops/targets are checked against each day's OHLC. If both are touched
    on one bar, the stop is assumed first (conservative convention).
    """
    d = data.copy()
    d["Desired_Position"] = d["Signal"].shift(1).fillna(0).astype(int)
    cash = float(initial_capital)
    units = 0.0
    entry_price = None
    entry_date = None
    entry_cost = 0.0
    equity_values, position_values, trade_rows = [], [], []
    pending_exit = False

    for i, (dt, row) in enumerate(d.iterrows()):
        open_price = float(row["Open"])
        high = float(row["High"])
        low = float(row["Low"])
        close = float(row["Close"])
        desired = int(row["Desired_Position"])
        exit_reason = None

        # A stop/target is evaluated on today's range for an existing position.
        if units > 0 and entry_price is not None:
            stop_price = entry_price * (1 - stop_pct) if stop_pct > 0 else None
            target_price = entry_price * (1 + target_pct) if target_pct > 0 else None
            stop_hit = stop_price is not None and low <= stop_price
            target_hit = target_price is not None and high >= target_price
            if stop_hit:
                # Gap-through stop: execute at open if open is below stop.
                fill = min(open_price, stop_price)
                exit_reason = "Stop-loss"
            elif target_hit:
                # Conservative target fill at target, unless price gaps above it.
                fill = max(open_price, target_price)
                exit_reason = "Take-profit"
            else:
                fill = close

            if exit_reason:
                proceeds = units * fill * (1 - fee_rate)
                pnl = proceeds - entry_cost
                trade_rows.append({
                    "Entry date": entry_date, "Exit date": dt,
                    "Entry price": entry_price, "Exit price": fill,
                    "Return (%)": ((fill / entry_price) - 1) * 100,
                    "Net P/L ($)": pnl, "Exit reason": exit_reason,
                })
                cash = proceeds
                units, entry_price, entry_date, entry_cost = 0.0, None, None, 0.0

        # Strategy signal changes are executed at today's open, provided no
        # protective exit already occurred on this bar.
        if units > 0 and desired == 0 and exit_reason is None:
            fill = open_price
            proceeds = units * fill * (1 - fee_rate)
            pnl = proceeds - entry_cost
            trade_rows.append({
                "Entry date": entry_date, "Exit date": dt,
                "Entry price": entry_price, "Exit price": fill,
                "Return (%)": ((fill / entry_price) - 1) * 100,
                "Net P/L ($)": pnl, "Exit reason": "Strategy signal",
            })
            cash = proceeds
            units, entry_price, entry_date, entry_cost = 0.0, None, None, 0.0

        if units == 0 and desired == 1 and exit_reason is None:
            fill = open_price
            units = cash / (fill * (1 + fee_rate))
            entry_cost = cash
            cash = 0.0
            entry_price, entry_date = fill, dt

            # Also evaluate protective levels on the entry session.
            # If both levels are touched in the same daily bar, assume stop first.
            same_day_stop = entry_price * (1 - stop_pct) if stop_pct > 0 else None
            same_day_target = entry_price * (1 + target_pct) if target_pct > 0 else None
            stop_hit = same_day_stop is not None and low <= same_day_stop
            target_hit = same_day_target is not None and high >= same_day_target
            if stop_hit or target_hit:
                if stop_hit:
                    protective_fill = same_day_stop
                    protective_reason = "Stop-loss"
                else:
                    protective_fill = same_day_target
                    protective_reason = "Take-profit"
                proceeds = units * protective_fill * (1 - fee_rate)
                pnl = proceeds - entry_cost
                trade_rows.append({
                    "Entry date": entry_date, "Exit date": dt,
                    "Entry price": entry_price, "Exit price": protective_fill,
                    "Return (%)": ((protective_fill / entry_price) - 1) * 100,
                    "Net P/L ($)": pnl, "Exit reason": protective_reason,
                })
                cash = proceeds
                units, entry_price, entry_date, entry_cost = 0.0, None, None, 0.0

        equity = cash + units * close
        equity_values.append(equity)
        position_values.append(1 if units > 0 else 0)

    d["Equity"] = equity_values
    d["Position"] = position_values
    d["Buy & Hold"] = initial_capital * (d["Close"] / d["Close"].iloc[0])
    d["Peak"] = d["Equity"].cummax()
    d["Drawdown"] = d["Equity"] / d["Peak"] - 1

    # Close an open position at the final close for a realized final report.
    if units > 0:
        dt = d.index[-1]
        fill = float(d["Close"].iloc[-1])
        proceeds = units * fill * (1 - fee_rate)
        pnl = proceeds - entry_cost
        trade_rows.append({
            "Entry date": entry_date, "Exit date": dt,
            "Entry price": entry_price, "Exit price": fill,
            "Return (%)": ((fill / entry_price) - 1) * 100,
            "Net P/L ($)": pnl, "Exit reason": "End of test",
        })
        d.loc[dt, "Equity"] = proceeds
        d["Peak"] = d["Equity"].cummax()
        d["Drawdown"] = d["Equity"] / d["Peak"] - 1

    trades = pd.DataFrame(trade_rows)
    return d, trades


def fmt_money(value):
    return f"${value:,.2f}"


# ----------------------------- UI -----------------------------------
st.title("StrategyLab")
st.caption("Backtesting historique de stratégies sur l'or et le pétrole — simulation, pas exécution réelle.")

with st.sidebar:
    st.header("Marché et période")
    asset_label = st.selectbox("Marché", ["Or — Gold Futures (GC=F)", "Pétrole WTI Futures (CL=F)"])
    symbol = "GC=F" if asset_label.startswith("Or") else "CL=F"
    today = date.today()
    start = st.date_input("Du", value=today - timedelta(days=365 * 5), max_value=today)
    end = st.date_input("Au", value=today, max_value=today)
    st.divider()
    st.header("Stratégie")
    strategy = st.selectbox("Type de stratégie", [
        "Moving average crossover", "RSI", "MACD", "Donchian breakout"
    ])
    if strategy == "Moving average crossover":
        p1 = st.number_input("Moyenne courte (jours)", 2, 100, 20)
        p2 = st.number_input("Moyenne longue (jours)", 3, 300, 50)
        strategy_name = "Croisement de moyennes mobiles"
    elif strategy == "RSI":
        p1 = st.number_input("Période RSI", 2, 50, 14)
        p2 = st.number_input("Seuil RSI", 5, 45, 30)
        strategy_name = "RSI (entrée sous seuil, sortie au seuil symétrique)"
    elif strategy == "MACD":
        p1 = st.number_input("EMA rapide", 2, 50, 12)
        p2 = st.number_input("EMA lente", 3, 100, 26)
        strategy_name = "MACD (12/26 avec signal 9)"
    else:
        p1 = st.number_input("Période breakout", 2, 100, 20)
        p2 = 0
        strategy_name = "Cassure Donchian"
    st.divider()
    st.header("Gestion du risque")
    capital = st.number_input("Capital initial ($)", min_value=100.0, value=10000.0, step=500.0)
    fee_pct = st.number_input("Frais par côté (%)", min_value=0.0, max_value=2.0, value=0.05, step=0.01)
    stop_pct = st.number_input("Stop-loss (%) — 0 = désactivé", min_value=0.0, max_value=50.0, value=0.0, step=0.5) / 100
    target_pct = st.number_input("Take-profit (%) — 0 = désactivé", min_value=0.0, max_value=100.0, value=0.0, step=0.5) / 100
    refresh = st.button("Actualiser les données maintenant", use_container_width=True)

if start >= end:
    st.error("La date de début doit être antérieure à la date de fin.")
    st.stop()
if strategy == "Moving average crossover" and p1 >= p2:
    st.error("La moyenne mobile courte doit être inférieure à la moyenne longue.")
    st.stop()
if strategy == "MACD" and p1 >= p2:
    st.error("L'EMA rapide doit être inférieure à l'EMA lente.")
    st.stop()
if refresh:
    load_market_data.clear()

with st.spinner("Chargement des données historiques..."):
    try:
        prices = load_market_data(symbol, start, end)
    except Exception as exc:
        st.error(f"Impossible de récupérer les données : {exc}")
        st.info("Vérifie ta connexion Internet et réessaie plus tard. La source de données peut limiter temporairement les téléchargements.")
        st.stop()

if prices.empty:
    st.error("Aucune donnée reçue pour ce marché et cette période.")
    st.stop()
if len(prices) < 35:
    st.error("Historique trop court pour produire une analyse sérieuse. Choisis une période plus longue.")
    st.stop()

prepared = add_indicators(prices, strategy, int(p1), int(p2))
if prepared["Signal"].sum() == 0 and prepared["Signal"].notna().all():
    st.warning("Aucun signal d'achat n'a été détecté avec ces paramètres.")

results, trades = run_backtest(prepared, float(capital), float(fee_pct) / 100, stop_pct, target_pct)
final_equity = float(results["Equity"].iloc[-1])
total_return = (final_equity / capital - 1) * 100
bh_return = (float(results["Buy & Hold"].iloc[-1]) / capital - 1) * 100
max_dd = float(results["Drawdown"].min()) * 100
closed = trades.copy()  # Toutes les lignes ont une sortie, y compris la liquidation finale.
win_rate = float((closed["Net P/L ($)"] > 0).mean() * 100) if not closed.empty else 0.0
gross_profit = float(closed.loc[closed["Net P/L ($)"] > 0, "Net P/L ($)"].sum())
gross_loss = abs(float(closed.loc[closed["Net P/L ($)"] < 0, "Net P/L ($)"].sum()))
profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

st.subheader(f"{asset_label} · {strategy_name}")
st.caption(f"{len(prices):,} séances · du {prices.index[0].date()} au {prices.index[-1].date()} · dernière donnée disponible selon le fournisseur")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Capital final", fmt_money(final_equity), f"{total_return:+.2f}%")
m2.metric("Buy & Hold", f"{bh_return:+.2f}%")
m3.metric("Drawdown maximal", f"{max_dd:.2f}%")
m4.metric("Taux de réussite", f"{win_rate:.1f}%")
m5, m6, m7, m8 = st.columns(4)
m5.metric("Transactions clôturées", len(closed))
m6.metric("Profit Factor", "∞" if np.isinf(profit_factor) else f"{profit_factor:.2f}")
m7.metric("P/L net", fmt_money(final_equity - capital))
m8.metric("Données", "Quotidiennes")

tab_chart, tab_trades, tab_data, tab_method = st.tabs(["Graphiques", "Transactions", "Données", "Méthodologie"])

with tab_chart:
    candle = go.Figure()
    candle.add_trace(go.Candlestick(
        x=results.index, open=results["Open"], high=results["High"],
        low=results["Low"], close=results["Close"], name="Prix"
    ))
    if strategy == "Moving average crossover":
        candle.add_trace(go.Scatter(x=results.index, y=results["Indicator_1"], name="Moyenne courte"))
        candle.add_trace(go.Scatter(x=results.index, y=results["Indicator_2"], name="Moyenne longue"))
    elif strategy == "MACD":
        candle.add_trace(go.Scatter(x=results.index, y=results["Indicator_1"], name="MACD", yaxis="y2"))
        candle.add_trace(go.Scatter(x=results.index, y=results["Indicator_2"], name="Signal MACD", yaxis="y2"))
        candle.update_layout(yaxis2=dict(title="MACD", overlaying="y", side="right", showgrid=False))
    elif strategy == "Donchian breakout":
        candle.add_trace(go.Scatter(x=results.index, y=results["Indicator_1"], name="Canal haut"))
        candle.add_trace(go.Scatter(x=results.index, y=results["Indicator_2"], name="Canal bas"))
    if not trades.empty:
        candle.add_trace(go.Scatter(
            x=trades["Entry date"], y=trades["Entry price"], mode="markers",
            marker=dict(symbol="triangle-up", size=10), name="Entrée"
        ))
        candle.add_trace(go.Scatter(
            x=trades["Exit date"], y=trades["Exit price"], mode="markers",
            marker=dict(symbol="triangle-down", size=10), name="Sortie"
        ))
    candle.update_layout(height=560, xaxis_rangeslider_visible=False, hovermode="x unified",
                         title="Prix historique et indicateurs")
    st.plotly_chart(candle, use_container_width=True)

    if strategy == "RSI":
        rsi_fig = go.Figure()
        rsi_fig.add_trace(go.Scatter(
            x=results.index, y=results["Indicator_1"],
            name="RSI", line=dict(width=2)
        ))
        rsi_fig.add_hline(y=float(p2), line_dash="dash", annotation_text="Seuil bas")
        rsi_fig.add_hline(y=100 - float(p2), line_dash="dash", annotation_text="Seuil haut")
        rsi_fig.update_layout(
            height=260, title="RSI — Relative Strength Index",
            yaxis=dict(title="RSI", range=[0, 100]),
            hovermode="x unified"
        )
        st.plotly_chart(rsi_fig, use_container_width=True)

    equity_fig = go.Figure()
    equity_fig.add_trace(go.Scatter(x=results.index, y=results["Equity"], name="Stratégie", fill="tozeroy"))
    equity_fig.add_trace(go.Scatter(x=results.index, y=results["Buy & Hold"], name="Buy & Hold"))
    equity_fig.update_layout(height=360, title="Évolution du capital", hovermode="x unified")
    st.plotly_chart(equity_fig, use_container_width=True)

    dd_fig = go.Figure()
    dd_fig.add_trace(go.Scatter(x=results.index, y=results["Drawdown"] * 100, name="Drawdown", fill="tozeroy"))
    dd_fig.update_layout(height=280, title="Drawdown (%)", yaxis_title="Baisse depuis le sommet (%)")
    st.plotly_chart(dd_fig, use_container_width=True)

with tab_trades:
    if trades.empty:
        st.info("Aucune transaction n'a été générée.")
    else:
        st.dataframe(trades, use_container_width=True, hide_index=True)
        st.download_button("Télécharger les transactions CSV", trades.to_csv(index=False).encode("utf-8"),
                           file_name="strategylab_trades.csv", mime="text/csv")

with tab_data:
    st.dataframe(results.tail(500), use_container_width=True)
    st.download_button("Télécharger les données et résultats CSV", results.to_csv().encode("utf-8"),
                       file_name="strategylab_backtest.csv", mime="text/csv")

with tab_method:
    st.markdown("""
**Conventions du moteur**

- Les signaux sont calculés à la clôture d'une séance et exécutés à l'ouverture de la séance suivante.
- Le moteur est long-only : il détient l'actif ou reste en liquidités, sans vente à découvert ni levier.
- Les frais sont appliqués à chaque entrée et sortie.
- Le stop-loss et le take-profit sont évalués avec les plus hauts et plus bas journaliers. Si les deux niveaux sont touchés pendant la même séance, le stop-loss est considéré touché en premier.
- Le portefeuille est investi à 100 % à chaque entrée. Les frais sont prélevés sur le montant investi.
- Les contrats à terme continus GC=F et CL=F sont des proxys : ils ne représentent pas nécessairement le prix spot ou le CFD du courtier du client.
- Les résultats historiques ne prédisent pas les performances futures. Le slippage, les spreads, le financement, les marges, les changements de contrat et les spécifications du courtier ne sont pas modélisés.
- Les données Yahoo Finance peuvent être retardées, incomplètes ou temporairement indisponibles. Le cache est conservé une heure et le bouton d'actualisation force un nouveau téléchargement.
""")

st.divider()
st.caption("StrategyLab · Outil de recherche historique uniquement · Pas de connexion à un courtier ni d'exécution d'ordres.")
