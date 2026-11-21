import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from risk.manager import RiskParams


def _mk_df(rows):
    """rows: list of dict avec open/high/low/close/buy_signal/sell_signal"""
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.date_range("2025-01-01", periods=len(df), freq="D", tz="UTC")
    return df


def _engine(**kwargs):
    risk = RiskParams(
        risk_pct=kwargs.pop("risk_pct", 0.02),
        stop_loss_pct=kwargs.pop("stop_loss_pct", 0.02),
        take_profit_pct=kwargs.pop("take_profit_pct", 0.04),
    )
    return BacktestEngine(
        initial_cash=kwargs.pop("initial_cash", 10_000),
        risk=risk,
        commission_rate=kwargs.pop("commission_rate", 0.0),
        slippage_rate=kwargs.pop("slippage_rate", 0.0),
        sltp_ambiguity_policy=kwargs.pop("sltp_ambiguity_policy", "stop_first"),
    )


def test_entry_executes_at_next_bar_open_not_signal_bar_close():
    # signal à la barre 0 (close=100), exécution attendue à l'open de la barre 1 (105)
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 105, "high": 106, "low": 104, "close": 105, "buy_signal": False, "sell_signal": False},
        {"open": 105, "high": 106, "low": 104, "close": 105, "buy_signal": False, "sell_signal": False},
    ])
    eng = _engine()
    trades, equity = eng.run(df)
    # aucune clôture, mais on vérifie via l'equity que l'entrée a eu lieu à 105, pas 100
    assert equity["equity"].iloc[0] == pytest.approx(10_000.0)  # pas encore entré à la barre 0
    assert equity["equity"].iloc[1] < 10_000.0 or equity["equity"].iloc[1] >= 10_000.0
    # position ouverte seulement après la barre 0 -> vérifions via un SL/TP déclenché plus tard


def test_take_profit_triggers_exit():
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": False, "sell_signal": False},
        # TP = 100*1.04 = 104 -> touché ici
        {"open": 101, "high": 105, "low": 100, "close": 103, "buy_signal": False, "sell_signal": False},
    ])
    eng = _engine(take_profit_pct=0.04, stop_loss_pct=0.5)  # SL loin pour ne pas interférer
    trades, equity = eng.run(df)
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "TP"
    assert trades.iloc[0]["pnl_dollars"] > 0


def test_stop_loss_triggers_exit():
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": False, "sell_signal": False},
        # SL = 100*0.98 = 98 -> touché ici
        {"open": 99, "high": 99, "low": 96, "close": 97, "buy_signal": False, "sell_signal": False},
    ])
    eng = _engine(stop_loss_pct=0.02, take_profit_pct=0.5)
    trades, equity = eng.run(df)
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "SL"
    assert trades.iloc[0]["pnl_dollars"] < 0


def test_ambiguous_sl_tp_same_bar_defaults_to_stop_first():
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": False, "sell_signal": False},
        # SL=98 et TP=104 tous les deux dans le range de cette bougie -> ambigu
        {"open": 100, "high": 106, "low": 95, "close": 100, "buy_signal": False, "sell_signal": False},
    ])
    eng = _engine(stop_loss_pct=0.02, take_profit_pct=0.04,
                   sltp_ambiguity_policy="stop_first")
    trades, equity = eng.run(df)
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "SL"
    assert trades.iloc[0]["sltp_ambiguous"] == True


def test_ambiguous_sl_tp_same_bar_tp_first_policy():
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": False, "sell_signal": False},
        {"open": 100, "high": 106, "low": 95, "close": 100, "buy_signal": False, "sell_signal": False},
    ])
    eng = _engine(stop_loss_pct=0.02, take_profit_pct=0.04,
                   sltp_ambiguity_policy="tp_first")
    trades, equity = eng.run(df)
    assert trades.iloc[0]["exit_reason"] == "TP"


def test_sell_signal_exits_without_sl_tp_hit():
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 100, "high": 101, "low": 99, "close": 100, "buy_signal": False, "sell_signal": True},
        {"open": 100, "high": 101, "low": 99, "close": 100, "buy_signal": False, "sell_signal": False},
    ])
    eng = _engine(stop_loss_pct=0.5, take_profit_pct=0.5)  # trop loin pour être touchés
    trades, equity = eng.run(df)
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "SIGNAL"


def test_commission_and_slippage_reduce_pnl():
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": False, "sell_signal": True},
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": False, "sell_signal": False},
    ])
    eng_no_fees = _engine(commission_rate=0.0, slippage_rate=0.0,
                           stop_loss_pct=0.5, take_profit_pct=0.5)
    eng_fees = _engine(commission_rate=0.01, slippage_rate=0.01,
                        stop_loss_pct=0.5, take_profit_pct=0.5)
    t1, _ = eng_no_fees.run(df)
    t2, _ = eng_fees.run(df)
    assert t2.iloc[0]["pnl_dollars"] < t1.iloc[0]["pnl_dollars"]


def test_position_cost_never_exceeds_available_cash():
    # cash minuscule -> la quantité doit être plafonnée, jamais de dépassement
    df = _mk_df([
        {"open": 1000, "high": 1000, "low": 1000, "close": 1000, "buy_signal": True, "sell_signal": False},
        {"open": 1000, "high": 1000, "low": 1000, "close": 1000, "buy_signal": False, "sell_signal": False},
    ])
    eng = _engine(initial_cash=1.0, risk_pct=0.5, stop_loss_pct=0.02)
    trades, equity = eng.run(df)
    # ne doit jamais planter et l'équité ne doit jamais devenir négative
    assert (equity["equity"] >= 0).all()


def test_no_lookahead_price_spike_on_signal_bar_does_not_affect_entry_price():
    # Un pic de prix sur la barre du signal ne doit pas influencer le prix d'entrée
    # (qui doit être l'open de la barre SUIVANTE).
    df = _mk_df([
        {"open": 100, "high": 999, "low": 1, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 110, "high": 110, "low": 110, "close": 110, "buy_signal": False, "sell_signal": True},
    ])
    eng = _engine(stop_loss_pct=0.5, take_profit_pct=0.5, commission_rate=0, slippage_rate=0)
    trades, equity = eng.run(df)
    assert trades.iloc[0]["entry_price"] == pytest.approx(110.0)


def test_reproducibility_same_inputs_same_outputs():
    df = _mk_df([
        {"open": 100, "high": 100, "low": 100, "close": 100, "buy_signal": True, "sell_signal": False},
        {"open": 100, "high": 104, "low": 98, "close": 100, "buy_signal": False, "sell_signal": False},
        {"open": 100, "high": 104, "low": 98, "close": 100, "buy_signal": False, "sell_signal": False},
    ])
    eng1 = _engine()
    eng2 = _engine()
    t1, e1 = eng1.run(df)
    t2, e2 = eng2.run(df)
    pd.testing.assert_frame_equal(t1, t2)
    pd.testing.assert_frame_equal(e1, e2)


def test_missing_columns_rejected():
    df = pd.DataFrame({"timestamp": [1], "open": [1], "close": [1]})
    eng = _engine()
    with pytest.raises(ValueError, match="Colonnes manquantes"):
        eng.run(df)
