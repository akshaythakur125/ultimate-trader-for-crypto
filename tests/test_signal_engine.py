from datetime import datetime

import pytest

from ultimate_trader.signal_engine import (
    DirectionBias,
    EntryPlanner,
    EntryType,
    ExecutionConditionBuilder,
    PositionSizer,
    RRAnalyzer,
    SignalContext,
    SignalGate,
    SignalGateResult,
    SignalQualityResult,
    SignalQualityScorer,
    SignalReport,
    StopPlanner,
    TargetPlanner,
)
from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.trade_plan import (
    ConditionType,
    EntryZone,
    ExecutionCondition,
    RiskRewardAnalysis,
    StopPlan,
    TargetPlan,
    TradePlan,
    TradeStatus,
)
from ultimate_trader.event_bus import (
    EventBus,
    EventType,
    get_default_bus,
    get_default_store,
    publish_system_event,
)


def make_ctx(**kwargs) -> SignalContext:
    fields = {
        "context_id": "SC-INT-TEST",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "validated_hypothesis_id": "RH-INT",
        "direction_bias": DirectionBias.LONG,
        "current_price": 100.0,
        "confidence_score": 60.0,
        "risk_score": 30.0,
        "uncertainty_score": 30.0,
        "expected_value_r": 2.0,
        "validation_passed": True,
        "volatility_score": 30.0,
    }
    fields.update(kwargs)
    return SignalContext(**fields)


class TestSignalIntegration:
    def test_full_signal_pipeline(self):
        ctx = make_ctx()

        entry = EntryPlanner().plan_entry(ctx)
        stop = StopPlanner().plan_stop(ctx, ctx.current_price)
        targets = TargetPlanner().plan_targets(ctx, ctx.current_price, stop.stop_loss_price)
        rr = RRAnalyzer().analyze(ctx.current_price, stop.stop_loss_price, targets.take_profit_1)

        quality = SignalQualityScorer().score(ctx, entry, stop, targets, rr)
        gate = SignalGate().evaluate(ctx, rr, quality, entry.entry_type)

        assert gate.approved_for_alert is True
        assert gate.approved_for_live_trade is False
        assert quality.quality_grade.value != "REJECT"

    def test_pipeline_rejects_weak_signal(self):
        ctx = make_ctx(
            validation_passed=False,
            expected_value_r=0.0,
            confidence_score=20.0,
            uncertainty_score=80.0,
        )

        entry = EntryPlanner().plan_entry(ctx)
        assert entry.entry_type == EntryType.NO_SAFE_ENTRY

        quality = SignalQualityScorer().score(ctx)
        assert quality.quality_grade.value == "REJECT"

        gate = SignalGate().evaluate(ctx, entry_type=entry.entry_type)
        assert gate.approved_for_alert is False

    def test_execution_conditions_created(self):
        ctx = make_ctx()
        builder = ExecutionConditionBuilder()
        conditions = builder.build_conditions(ctx)
        assert len(conditions) == 5
        assert all(isinstance(c, ExecutionCondition) for c in conditions)

    def test_trade_plan_assembled(self):
        ctx = make_ctx()
        entry = EntryPlanner().plan_entry(ctx)
        stop = StopPlanner().plan_stop(ctx, ctx.current_price)
        targets = TargetPlanner().plan_targets(ctx, ctx.current_price, stop.stop_loss_price)
        rr = RRAnalyzer().analyze(ctx.current_price, stop.stop_loss_price, targets.take_profit_1)
        sizing = PositionSizer().size(ctx)
        builder = ExecutionConditionBuilder()
        conditions = builder.build_conditions(ctx)

        plan = TradePlan(
            trade_plan_id="TP-INT-001",
            symbol=ctx.symbol,
            direction=ctx.direction_bias,
            timeframe=ctx.timeframe,
            entry_zone=entry,
            stop_plan=stop,
            target_plan=targets,
            rr_analysis=rr,
            execution_conditions=conditions,
            position_sizing=sizing,
            trade_status=TradeStatus.READY_FOR_REVIEW,
            reasons_for_trade=["Clear setup", "Good RR"],
            reasons_against_trade=["High volatility"],
            final_summary="Test trade plan",
        )
        assert plan.trade_plan_id == "TP-INT-001"
        assert plan.trade_status == TradeStatus.READY_FOR_REVIEW

    def test_signal_report_generated(self):
        ctx = make_ctx()
        report = SignalReport(
            report_id="SR-001",
            signal_context=ctx,
            final_recommendation="PAPER_TRADE_CANDIDATE",
            explanation="Test report",
        )
        assert report.report_id == "SR-001"


class TestSignalEvents:
    def test_signal_events_published(self):
        bus = get_default_bus()
        store = get_default_store()
        received = []

        def handler(event):
            received.append(event.event_type)

        bus.subscribe(EventType.SIGNAL_CANDIDATE_CREATED, handler)

        publish_system_event(
            EventType.SIGNAL_CANDIDATE_CREATED,
            "test",
            {"signal_context_id": "SC-001"},
        )

        assert EventType.SIGNAL_CANDIDATE_CREATED in received

    def test_rejected_signal_event_published(self):
        bus = get_default_bus()
        received = []

        def handler(event):
            received.append(event.event_type)

        bus.subscribe(EventType.SIGNAL_REJECTED, handler)

        publish_system_event(
            EventType.SIGNAL_REJECTED,
            "test",
            {"reason": "Validation failed"},
        )

        assert EventType.SIGNAL_REJECTED in received

    def test_live_trade_blocked_event_published(self):
        bus = get_default_bus()
        received = []

        def handler(event):
            received.append(event.event_type)

        bus.subscribe(EventType.LIVE_TRADE_BLOCKED, handler)

        publish_system_event(
            EventType.LIVE_TRADE_BLOCKED,
            "test",
            {"reason": "Live trading not enabled"},
        )

        assert EventType.LIVE_TRADE_BLOCKED in received
