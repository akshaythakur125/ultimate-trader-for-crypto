from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.signal_engine.rr_analyzer import RRAnalyzer
from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.signal_quality import (
    SignalQualityResult,
)
from ultimate_trader.signal_engine.trade_plan import (
    EntryType,
    ExecutionCondition,
    RiskRewardAnalysis,
)


class SignalGateResult(BaseModel):
    approved_for_alert: bool = False
    approved_for_paper_trade: bool = False
    approved_for_live_trade: bool = False
    failed_reasons: list[str] = Field(default_factory=list)
    passed_checks: list[str] = Field(default_factory=list)
    gate_summary: str = ""


class SignalGate:
    MIN_CONFIDENCE = 40.0
    MAX_RISK = 75.0
    MAX_UNCERTAINTY = 70.0

    def evaluate(
        self,
        ctx: SignalContext,
        rr_analysis: Optional[RiskRewardAnalysis] = None,
        quality: Optional[SignalQualityResult] = None,
        entry_type: Optional[EntryType] = None,
        conditions: Optional[list[ExecutionCondition]] = None,
    ) -> SignalGateResult:
        passed = True
        failed_reasons = []
        passed_checks = []

        if not ctx.validation_passed:
            passed = False
            failed_reasons.append("Validation not passed")

        if ctx.validation_passed:
            passed_checks.append("Validation passed")

        if ctx.expected_value_r <= 0:
            passed = False
            failed_reasons.append(f"Non-positive expected value ({ctx.expected_value_r})")
        else:
            passed_checks.append(f"Positive expected value ({ctx.expected_value_r})")

        if ctx.confidence_score < self.MIN_CONFIDENCE:
            passed = False
            failed_reasons.append(f"Confidence below minimum ({ctx.confidence_score} < {self.MIN_CONFIDENCE})")
        else:
            passed_checks.append(f"Confidence acceptable ({ctx.confidence_score})")

        if ctx.risk_score > self.MAX_RISK:
            passed = False
            failed_reasons.append(f"Risk score exceeds maximum ({ctx.risk_score} > {self.MAX_RISK})")
        else:
            passed_checks.append(f"Risk within limits ({ctx.risk_score})")

        if ctx.uncertainty_score > self.MAX_UNCERTAINTY:
            passed = False
            failed_reasons.append(f"Uncertainty exceeds maximum ({ctx.uncertainty_score} > {self.MAX_UNCERTAINTY})")
        else:
            passed_checks.append(f"Uncertainty acceptable ({ctx.uncertainty_score})")

        if rr_analysis:
            if not rr_analysis.meets_minimum_rr:
                passed = False
                failed_reasons.append(
                    f"R:R below minimum ({rr_analysis.rr_ratio:.1f} < {RRAnalyzer.MINIMUM_RR})"
                )
            else:
                passed_checks.append(f"R:R meets minimum ({rr_analysis.rr_ratio:.1f})")

        if entry_type and entry_type == EntryType.NO_SAFE_ENTRY:
            passed = False
            failed_reasons.append("No safe entry available")

        if entry_type and entry_type != EntryType.NO_SAFE_ENTRY:
            passed_checks.append(f"Entry available ({entry_type.value})")

        if quality:
            if quality.quality_grade.value in ("REJECT",):
                passed = False
                failed_reasons.append(f"Signal quality grade: {quality.quality_grade.value}")
            else:
                passed_checks.append(f"Signal quality acceptable ({quality.quality_grade.value})")

        if conditions:
            blockers = [c for c in conditions if c.condition_type.value == "BLOCKER" and not c.is_satisfied]
            required_failed = [c for c in conditions if c.condition_type.value == "REQUIRED" and not c.is_satisfied]
            for c in blockers + required_failed:
                passed = False
                failed_reasons.append(c.failure_reason or c.description)
            satisfied = [c for c in conditions if c.is_satisfied]
            for c in satisfied:
                passed_checks.append(c.description)

        return SignalGateResult(
            approved_for_alert=passed,
            approved_for_paper_trade=passed and quality is not None and quality.quality_grade.value in ("A", "A_PLUS", "B"),
            approved_for_live_trade=False,
            failed_reasons=failed_reasons,
            passed_checks=passed_checks,
            gate_summary="Approved" if passed else f"Rejected ({len(failed_reasons)} failures)",
        )
