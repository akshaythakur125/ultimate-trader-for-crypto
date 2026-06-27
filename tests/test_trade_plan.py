import pytest

from ultimate_trader.signal_engine.signal_context import (
    DirectionBias,
    SignalContext,
)
from ultimate_trader.signal_engine.trade_plan import (
    CancellationRule,
    ConditionType,
    EntryType,
    EntryZone,
    ExecutionCondition,
    PositionSizingSuggestion,
    RiskRewardAnalysis,
    StopPlan,
    StopType,
    TargetPlan,
    TradePlan,
    TradeStatus,
)


class TestSignalContext:
    def test_context_created(self):
        ctx = SignalContext(
            context_id="SC-001",
            symbol="BTCUSDT",
            timeframe="1h",
            validated_hypothesis_id="RH-001",
            direction_bias=DirectionBias.LONG,
        )
        assert ctx.context_id == "SC-001"
        assert ctx.direction_bias == DirectionBias.LONG

    def test_context_defaults(self):
        ctx = SignalContext(
            context_id="SC-002",
            symbol="ETHUSDT",
            timeframe="15m",
            validated_hypothesis_id="RH-002",
            direction_bias=DirectionBias.SHORT,
        )
        assert ctx.validation_passed is False


class TestTradePlanModels:
    def test_entry_zone_created(self):
        zone = EntryZone(
            entry_zone_id="EZ-001",
            symbol="BTCUSDT",
            direction=DirectionBias.LONG,
            entry_type=EntryType.LIMIT_ZONE,
        )
        assert zone.entry_type == EntryType.LIMIT_ZONE

    def test_stop_plan_created(self):
        stop = StopPlan(stop_id="SP-001", stop_loss_price=50000.0)
        assert stop.stop_loss_price == 50000.0

    def test_target_plan_created(self):
        target = TargetPlan(
            target_id="TP-001",
            take_profit_1=60000.0,
            target_realism_score=75.0,
        )
        assert target.take_profit_1 == 60000.0

    def test_rr_analysis_created(self):
        rr = RiskRewardAnalysis(
            rr_id="RR-001",
            rr_ratio=5.0,
            meets_minimum_rr=True,
        )
        assert rr.meets_minimum_rr is True

    def test_execution_condition_created(self):
        cond = ExecutionCondition(
            condition_id="EC-001",
            description="Test condition",
            condition_type=ConditionType.REQUIRED,
            is_satisfied=True,
        )
        assert cond.is_satisfied is True

    def test_cancellation_rule_created(self):
        rule = CancellationRule(
            rule_id="CR-001",
            description="Cancel if X",
            reason="X happened",
        )
        assert rule.cancel_if_triggered is True

    def test_position_sizing_created(self):
        sizing = PositionSizingSuggestion(
            sizing_id="PS-001",
            suggested_risk_percent=1.0,
            sizing_reason="Standard sizing",
        )
        assert sizing.suggested_risk_percent == 1.0

    def test_trade_plan_created(self):
        plan = TradePlan(
            trade_plan_id="TP-001",
            symbol="BTCUSDT",
            direction=DirectionBias.LONG,
            timeframe="1h",
            final_summary="Test plan",
        )
        assert plan.trade_status == TradeStatus.DRAFT
