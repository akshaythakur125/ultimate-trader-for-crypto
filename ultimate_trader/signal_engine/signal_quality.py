from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.trade_plan import (
    EntryZone,
    RiskRewardAnalysis,
    StopPlan,
    TargetPlan,
)


class QualityGrade(str, Enum):
    A_PLUS = "A_PLUS"
    A = "A"
    B = "B"
    C = "C"
    REJECT = "REJECT"


class SignalQualityResult(BaseModel):
    signal_quality_score: float = 0.0
    quality_grade: QualityGrade = QualityGrade.REJECT
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    quality_summary: str = ""


class SignalQualityScorer:
    def score(
        self,
        ctx: SignalContext,
        entry_zone: Optional[EntryZone] = None,
        stop_plan: Optional[StopPlan] = None,
        target_plan: Optional[TargetPlan] = None,
        rr_analysis: Optional[RiskRewardAnalysis] = None,
    ) -> SignalQualityResult:
        score = 30.0
        strengths = []
        weaknesses = []

        if ctx.validation_passed:
            score += 15.0
            strengths.append("Hypothesis passed validation")
        else:
            weaknesses.append("Hypothesis not validated")

        if ctx.expected_value_r > 0:
            score += 10.0
            strengths.append(f"Positive expected value ({ctx.expected_value_r})")
        else:
            weaknesses.append("Non-positive expected value")

        if ctx.confidence_score >= 50:
            score += 5.0
            strengths.append(f"Adequate confidence ({ctx.confidence_score})")
        else:
            weaknesses.append(f"Low confidence ({ctx.confidence_score})")

        if ctx.uncertainty_score < 50:
            score += 5.0
            strengths.append(f"Low uncertainty ({ctx.uncertainty_score})")
        else:
            weaknesses.append(f"High uncertainty ({ctx.uncertainty_score})")

        if entry_zone and entry_zone.entry_type.value != "NO_SAFE_ENTRY":
            score += 10.0
            strengths.append(f"Entry type: {entry_zone.entry_type.value}")
        else:
            weaknesses.append("No safe entry available")

        if stop_plan and not stop_plan.stop_is_too_obvious:
            score += 5.0
            strengths.append("Stop level is not obvious")
        if stop_plan and stop_plan.stop_warning:
            weaknesses.append(f"Stop warning: {stop_plan.stop_warning}")

        if target_plan and target_plan.target_realism_score >= 50:
            score += 5.0
            strengths.append(f"Target realistic ({target_plan.target_realism_score})")
        else:
            weaknesses.append("Target realism low")

        if rr_analysis:
            if rr_analysis.meets_preferred_rr:
                score += 10.0
                strengths.append(f"Preferred R:R met ({rr_analysis.rr_ratio:.1f})")
            elif rr_analysis.meets_minimum_rr:
                score += 5.0
                strengths.append(f"Minimum R:R met ({rr_analysis.rr_ratio:.1f})")
            else:
                weaknesses.append(f"R:R below minimum ({rr_analysis.rr_ratio:.1f})")

        if ctx.contradiction_score and ctx.contradiction_score > 50:
            score -= 10.0
            weaknesses.append(f"High contradiction score ({ctx.contradiction_score})")

        if ctx.memory_support_score is not None and ctx.memory_support_score >= 50:
            score += 5.0
            strengths.append(f"Memory support ({ctx.memory_support_score})")
        elif ctx.memory_support_score is not None:
            weaknesses.append(f"Weak memory support ({ctx.memory_support_score})")

        score = max(0.0, min(100.0, score))

        grade = self._assign_grade(score)
        summary = f"Quality score: {score:.0f}/100 — Grade: {grade.value}"

        return SignalQualityResult(
            signal_quality_score=round(score, 2),
            quality_grade=grade,
            strengths=strengths,
            weaknesses=weaknesses,
            quality_summary=summary,
        )

    def _assign_grade(self, score: float) -> QualityGrade:
        if score >= 90:
            return QualityGrade.A_PLUS
        if score >= 75:
            return QualityGrade.A
        if score >= 60:
            return QualityGrade.B
        if score >= 45:
            return QualityGrade.C
        return QualityGrade.REJECT
