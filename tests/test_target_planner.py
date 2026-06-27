import pytest

from ultimate_trader.signal_engine.target_planner import TargetPlanner
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
    }
    fields.update(kwargs)
    return SignalContext(**fields)


class TestTargetPlanner:
    def test_long_targets_above_entry(self):
        planner = TargetPlanner()
        ctx = make_ctx(direction_bias=DirectionBias.LONG)
        targets = planner.plan_targets(ctx, 100.0, 95.0)
        assert targets.take_profit_1 > 100.0
        assert targets.expected_reward_r > 0

    def test_short_targets_below_entry(self):
        planner = TargetPlanner()
        ctx = make_ctx(direction_bias=DirectionBias.SHORT)
        targets = planner.plan_targets(ctx, 100.0, 105.0)
        assert targets.take_profit_1 < 100.0
        assert targets.expected_reward_r > 0

    def test_target_realism_scored(self):
        planner = TargetPlanner()
        ctx = make_ctx(direction_bias=DirectionBias.LONG)
        targets = planner.plan_targets(ctx, 100.0, 95.0)
        assert 0 <= targets.target_realism_score <= 100

    def test_target_realism_lower_when_high_volatility(self):
        planner = TargetPlanner()
        ctx_low_vol = make_ctx(direction_bias=DirectionBias.LONG, volatility_score=20)
        ctx_high_vol = make_ctx(direction_bias=DirectionBias.LONG, volatility_score=80)
        tp_low = planner.plan_targets(ctx_low_vol, 100.0, 95.0)
        tp_high = planner.plan_targets(ctx_high_vol, 100.0, 95.0)
        assert tp_low.target_realism_score >= tp_high.target_realism_score

    def test_partial_exit_plan(self):
        planner = TargetPlanner()
        ctx = make_ctx(direction_bias=DirectionBias.LONG)
        targets = planner.plan_targets(ctx, 100.0, 95.0)
        assert targets.partial_exit_plan is not None

    def test_no_risk_target_at_entry(self):
        planner = TargetPlanner()
        ctx = make_ctx(direction_bias=DirectionBias.LONG)
        targets = planner.plan_targets(ctx, 100.0, 100.0)
        assert targets.expected_reward_r == 0.0
