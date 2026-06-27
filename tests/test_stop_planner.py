import pytest

from ultimate_trader.signal_engine.stop_planner import InvalidStopError, StopPlanner
from ultimate_trader.signal_engine.signal_context import (
    DirectionBias,
    SignalContext,
)


def make_ctx(**kwargs) -> SignalContext:
    fields = {
        "context_id": "SC-TEST",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "validated_hypothesis_id": "RH-TEST",
        "direction_bias": DirectionBias.LONG,
        "current_price": 100.0,
        "volatility_score": 30.0,
        "uncertainty_score": 20.0,
    }
    fields.update(kwargs)
    return SignalContext(**fields)


class TestStopPlanner:
    def test_stop_created_for_long(self):
        planner = StopPlanner()
        ctx = make_ctx(direction_bias=DirectionBias.LONG, volatility_score=30)
        stop = planner.plan_stop(ctx, 100.0)
        assert stop.stop_loss_price < 100.0
        assert stop.distance_from_entry_percent > 0

    def test_stop_created_for_short(self):
        planner = StopPlanner()
        ctx = make_ctx(direction_bias=DirectionBias.SHORT, volatility_score=30)
        stop = planner.plan_stop(ctx, 100.0)
        assert stop.stop_loss_price > 100.0

    def test_invalid_entry_price_raises_error(self):
        planner = StopPlanner()
        ctx = make_ctx()
        with pytest.raises(InvalidStopError):
            planner.plan_stop(ctx, 0.0)

    def test_stop_warning_for_too_wide(self):
        planner = StopPlanner()
        ctx = make_ctx(volatility_score=200)
        stop = planner.plan_stop(ctx, 100.0)
        assert stop.stop_warning is not None

    def test_stop_has_reason(self):
        planner = StopPlanner()
        ctx = make_ctx()
        stop = planner.plan_stop(ctx, 100.0)
        assert len(stop.stop_reason) > 0
