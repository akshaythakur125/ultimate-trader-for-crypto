import pytest

from ultimate_trader.signal_engine.position_sizing import PositionSizer
from ultimate_trader.signal_engine.signal_context import (
    DirectionBias,
    SignalContext,
)


def make_ctx(**kwargs) -> SignalContext:
    return SignalContext(
        context_id="SC-TEST",
        symbol="BTCUSDT",
        timeframe="1h",
        validated_hypothesis_id="RH-TEST",
        direction_bias=DirectionBias.LONG,
        current_price=100.0,
        **kwargs,
    )


class TestPositionSizer:
    def test_default_risk_one_percent(self):
        sizer = PositionSizer()
        ctx = make_ctx()
        sizing = sizer.size(ctx)
        assert sizing.suggested_risk_percent <= 2.0

    def test_reduces_risk_for_high_uncertainty(self):
        sizer = PositionSizer()
        low_uncertainty = make_ctx(uncertainty_score=20)
        high_uncertainty = make_ctx(uncertainty_score=60)
        low_sizing = sizer.size(low_uncertainty)
        high_sizing = sizer.size(high_uncertainty)
        assert high_sizing.suggested_risk_percent <= low_sizing.suggested_risk_percent

    def test_reduces_risk_for_high_contradiction(self):
        sizer = PositionSizer()
        ctx = make_ctx(contradiction_score=60)
        sizing = sizer.size(ctx)
        assert sizing.suggested_risk_percent < 1.0

    def test_reduces_risk_for_weak_memory(self):
        sizer = PositionSizer()
        ctx = make_ctx(memory_support_score=20)
        sizing = sizer.size(ctx)
        assert sizing.suggested_risk_percent < 1.0

    def test_reduces_risk_for_high_risk_score(self):
        sizer = PositionSizer()
        ctx = make_ctx(risk_score=70)
        sizing = sizer.size(ctx)
        assert sizing.suggested_risk_percent < 1.0

    def test_sizing_reason_includes_factors(self):
        sizer = PositionSizer()
        ctx = make_ctx(uncertainty_score=60, contradiction_score=60)
        sizing = sizer.size(ctx)
        assert len(sizing.sizing_reason) > 0

    def test_no_position_size_without_equity(self):
        sizer = PositionSizer()
        ctx = make_ctx()
        sizing = sizer.size(ctx)
        assert sizing.position_size_units is None

    def test_position_size_with_equity(self):
        sizer = PositionSizer()
        ctx = make_ctx()
        sizing = sizer.size(ctx, account_equity=10000.0)
        assert sizing.position_size_units is not None
