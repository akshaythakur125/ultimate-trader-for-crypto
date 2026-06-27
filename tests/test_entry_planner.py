import pytest

from ultimate_trader.signal_engine.entry_planner import EntryPlanner, NoSafeEntryError
from ultimate_trader.signal_engine.signal_context import (
    DirectionBias,
    SignalContext,
)
from ultimate_trader.signal_engine.trade_plan import EntryType


def make_ctx(**kwargs) -> SignalContext:
    fields = {
        "context_id": "SC-TEST",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "validated_hypothesis_id": "RH-TEST",
        "direction_bias": DirectionBias.LONG,
        "current_price": 100.0,
        "volatility_score": 30.0,
        "liquidity_score": 50.0,
        "uncertainty_score": 20.0,
        "risk_score": 20.0,
        "expected_value_r": 2.0,
        "validation_passed": True,
    }
    fields.update(kwargs)
    return SignalContext(**fields)


class TestEntryPlanner:
    def test_returns_entry_zone_for_valid_context(self):
        planner = EntryPlanner()
        ctx = make_ctx()
        zone = planner.plan_entry(ctx)
        assert zone.entry_type != EntryType.NO_SAFE_ENTRY
        assert zone.entry_min > 0

    def test_returns_no_safe_entry_when_validation_failed(self):
        planner = EntryPlanner()
        ctx = make_ctx(validation_passed=False)
        zone = planner.plan_entry(ctx)
        assert zone.entry_type == EntryType.NO_SAFE_ENTRY

    def test_returns_no_safe_entry_when_uncertainty_high(self):
        planner = EntryPlanner()
        ctx = make_ctx(uncertainty_score=80)
        zone = planner.plan_entry(ctx)
        assert zone.entry_type == EntryType.NO_SAFE_ENTRY

    def test_returns_no_safe_entry_when_risk_high(self):
        planner = EntryPlanner()
        ctx = make_ctx(risk_score=80)
        zone = planner.plan_entry(ctx)
        assert zone.entry_type == EntryType.NO_SAFE_ENTRY

    def test_returns_no_safe_entry_when_ev_non_positive(self):
        planner = EntryPlanner()
        ctx = make_ctx(expected_value_r=0.0)
        zone = planner.plan_entry(ctx)
        assert zone.entry_type == EntryType.NO_SAFE_ENTRY

    def test_returns_no_safe_entry_when_no_trade_dominant(self):
        planner = EntryPlanner()
        ctx = make_ctx(no_trade_probability=0.7)
        zone = planner.plan_entry(ctx)
        assert zone.entry_type == EntryType.NO_SAFE_ENTRY

    def test_entry_zone_has_entry_reason(self):
        planner = EntryPlanner()
        ctx = make_ctx()
        zone = planner.plan_entry(ctx)
        assert len(zone.entry_reason) > 0

    def test_entry_produces_entry_min_max(self):
        planner = EntryPlanner()
        ctx = make_ctx(current_price=50000.0)
        zone = planner.plan_entry(ctx)
        if zone.entry_type != EntryType.NO_SAFE_ENTRY:
            assert zone.entry_min < zone.entry_max
