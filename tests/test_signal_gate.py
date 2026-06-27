import pytest

from ultimate_trader.signal_engine.rr_analyzer import RRAnalyzer
from ultimate_trader.signal_engine.signal_context import (
    DirectionBias,
    SignalContext,
)
from ultimate_trader.signal_engine.signal_gate import SignalGate, SignalGateResult
from ultimate_trader.signal_engine.signal_quality import (
    QualityGrade,
    SignalQualityResult,
    SignalQualityScorer,
)
from ultimate_trader.signal_engine.trade_plan import (
    EntryType,
    ExecutionCondition,
    RiskRewardAnalysis,
)


def make_ctx(**kwargs) -> SignalContext:
    fields = {
        "context_id": "SC-TEST",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "validated_hypothesis_id": "RH-TEST",
        "direction_bias": DirectionBias.LONG,
        "current_price": 100.0,
        "confidence_score": 60.0,
        "risk_score": 30.0,
        "uncertainty_score": 30.0,
        "expected_value_r": 2.0,
        "validation_passed": True,
    }
    fields.update(kwargs)
    return SignalContext(**fields)


class TestSignalGate:
    def test_rejects_unvalidated_context(self):
        gate = SignalGate()
        ctx = make_ctx(validation_passed=False)
        result = gate.evaluate(ctx)
        assert result.approved_for_alert is False
        assert any("Validation not passed" in r for r in result.failed_reasons)

    def test_rejects_negative_ev(self):
        gate = SignalGate()
        ctx = make_ctx(expected_value_r=0.0)
        result = gate.evaluate(ctx)
        assert result.approved_for_alert is False
        assert any("expected value" in r.lower() for r in result.failed_reasons)

    def test_rejects_rr_below_3(self):
        gate = SignalGate()
        ctx = make_ctx()
        rr = RiskRewardAnalysis(
            rr_id="RR-TEST",
            rr_ratio=2.0,
            meets_minimum_rr=False,
            meets_preferred_rr=False,
        )
        result = gate.evaluate(ctx, rr_analysis=rr)
        assert result.approved_for_alert is False
        assert any("R:R" in r for r in result.failed_reasons)

    def test_rejects_low_confidence(self):
        gate = SignalGate()
        ctx = make_ctx(confidence_score=20.0)
        result = gate.evaluate(ctx)
        assert result.approved_for_alert is False

    def test_rejects_high_risk(self):
        gate = SignalGate()
        ctx = make_ctx(risk_score=80.0)
        result = gate.evaluate(ctx)
        assert result.approved_for_alert is False

    def test_rejects_high_uncertainty(self):
        gate = SignalGate()
        ctx = make_ctx(uncertainty_score=80.0)
        result = gate.evaluate(ctx)
        assert result.approved_for_alert is False

    def test_rejects_no_safe_entry(self):
        gate = SignalGate()
        ctx = make_ctx()
        result = gate.evaluate(ctx, entry_type=EntryType.NO_SAFE_ENTRY)
        assert result.approved_for_alert is False

    def test_approves_valid_context(self):
        gate = SignalGate()
        ctx = make_ctx()
        rr = RiskRewardAnalysis(
            rr_id="RR-TEST",
            rr_ratio=5.0,
            meets_minimum_rr=True,
            meets_preferred_rr=True,
        )
        quality = SignalQualityResult(
            signal_quality_score=80.0,
            quality_grade=QualityGrade.A,
        )
        result = gate.evaluate(
            ctx,
            rr_analysis=rr,
            quality=quality,
            entry_type=EntryType.LIMIT_ZONE,
        )
        assert result.approved_for_alert is True

    def test_never_approves_live_trading(self):
        gate = SignalGate()
        ctx = make_ctx()
        rr = RiskRewardAnalysis(
            rr_id="RR-TEST",
            rr_ratio=5.0,
            meets_minimum_rr=True,
            meets_preferred_rr=True,
        )
        quality = SignalQualityResult(
            signal_quality_score=90.0,
            quality_grade=QualityGrade.A_PLUS,
        )
        result = gate.evaluate(
            ctx,
            rr_analysis=rr,
            quality=quality,
            entry_type=EntryType.LIMIT_ZONE,
        )
        assert result.approved_for_live_trade is False

    def test_gate_summary_present(self):
        gate = SignalGate()
        ctx = make_ctx()
        result = gate.evaluate(ctx)
        assert len(result.gate_summary) > 0


class TestSignalQualityScorer:
    def test_grades_weak_plan_as_reject(self):
        scorer = SignalQualityScorer()
        ctx = make_ctx(
            validation_passed=False,
            expected_value_r=0.0,
            confidence_score=20.0,
            uncertainty_score=80.0,
        )
        result = scorer.score(ctx)
        assert result.quality_grade == QualityGrade.REJECT

    def test_grades_strong_plan_high(self):
        scorer = SignalQualityScorer()
        ctx = make_ctx()
        rr = RiskRewardAnalysis(
            rr_id="RR-TEST",
            rr_ratio=5.0,
            meets_minimum_rr=True,
            meets_preferred_rr=True,
        )
        from ultimate_trader.signal_engine.trade_plan import EntryZone, StopPlan, TargetPlan
        entry = EntryZone(
            entry_zone_id="EZ-TEST",
            symbol="BTCUSDT",
            direction=DirectionBias.LONG,
            entry_type=EntryType.LIMIT_ZONE,
        )
        stop = StopPlan(stop_id="SP-TEST", stop_loss_price=99.0)
        target = TargetPlan(
            target_id="TP-TEST",
            take_profit_1=105.0,
            target_realism_score=80.0,
        )
        result = scorer.score(ctx, entry, stop, target, rr)
        assert result.quality_grade in (QualityGrade.A, QualityGrade.A_PLUS, QualityGrade.B)

    def test_strengths_and_weaknesses_populated(self):
        scorer = SignalQualityScorer()
        ctx = make_ctx(validation_passed=False)
        result = scorer.score(ctx)
        assert len(result.weaknesses) > 0
