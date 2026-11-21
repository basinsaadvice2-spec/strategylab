import pytest
from risk.position_sizing import size_position
from risk.manager import RiskParams


def test_sizing_matches_spec_example():
    # 10 000 $ x 2% = 200 $ de risque théorique par trade (exemple du cahier des charges)
    qty, risk_dollars = size_position(cash=10_000, entry_price=100,
                                       risk_pct=0.02, stop_loss_pct=0.02)
    assert risk_dollars == pytest.approx(200.0)
    # distance du stop = 100 * 2% = 2 -> quantité = 200 / 2 = 100
    assert qty == pytest.approx(100.0)


def test_sizing_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        size_position(cash=0, entry_price=100, risk_pct=0.02, stop_loss_pct=0.02)
    with pytest.raises(ValueError):
        size_position(cash=10_000, entry_price=100, risk_pct=1.5, stop_loss_pct=0.02)
    with pytest.raises(ValueError):
        size_position(cash=10_000, entry_price=100, risk_pct=0.02, stop_loss_pct=0)


def test_risk_params_price_levels():
    r = RiskParams(risk_pct=0.02, stop_loss_pct=0.02, take_profit_pct=0.04)
    assert r.stop_loss_price(100) == pytest.approx(98.0)
    assert r.take_profit_price(100) == pytest.approx(104.0)


def test_risk_params_rejects_out_of_range():
    with pytest.raises(ValueError):
        RiskParams(risk_pct=0, stop_loss_pct=0.02, take_profit_pct=0.04)
    with pytest.raises(ValueError):
        RiskParams(risk_pct=0.02, stop_loss_pct=1.5, take_profit_pct=0.04)
