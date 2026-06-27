from enum import Enum
from typing import Optional

from pydantic import BaseModel


class UtilityGrade(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    MARGINAL = "MARGINAL"
    BAD = "BAD"
    NO_TRADE = "NO_TRADE"


class RiskAdjustedUtilityResult(BaseModel):
    raw_expected_value_r: float
    uncertainty_penalty: float = 0.0
    drawdown_penalty: float = 0.0
    contradiction_penalty: float = 0.0
    memory_penalty: float = 0.0
    final_utility_score: float
    utility_grade: UtilityGrade
    utility_summary: str = ""


class RiskAdjustedUtilityEngine:
    def calculate(
        self,
        raw_expected_value_r: float,
        uncertainty_score: float = 50.0,
        drawdown_risk: float = 50.0,
        contradiction_score: float = 0.0,
        memory_support_score: float = 50.0,
        no_trade_probability: float = 0.0,
    ) -> RiskAdjustedUtilityResult:
        uncertainty_penalty = uncertainty_score * 0.005
        drawdown_penalty = drawdown_risk * 0.005
        contradiction_penalty = contradiction_score * 0.008
        memory_penalty = max(0.0, (50.0 - memory_support_score) * 0.004)

        total_penalty = (
            uncertainty_penalty
            + drawdown_penalty
            + contradiction_penalty
            + memory_penalty
        )

        utility = raw_expected_value_r - total_penalty

        if no_trade_probability > 0.5:
            grade = UtilityGrade.NO_TRADE
        elif utility > 1.0:
            grade = UtilityGrade.EXCELLENT
        elif utility > 0.5:
            grade = UtilityGrade.GOOD
        elif utility > 0.0:
            grade = UtilityGrade.MARGINAL
        elif utility > -0.5:
            grade = UtilityGrade.BAD
        else:
            grade = UtilityGrade.NO_TRADE

        return RiskAdjustedUtilityResult(
            raw_expected_value_r=round(raw_expected_value_r, 3),
            uncertainty_penalty=round(uncertainty_penalty, 3),
            drawdown_penalty=round(drawdown_penalty, 3),
            contradiction_penalty=round(contradiction_penalty, 3),
            memory_penalty=round(memory_penalty, 3),
            final_utility_score=round(utility, 3),
            utility_grade=grade,
            utility_summary=(
                f"Raw EV={raw_expected_value_r:+.3f}R → "
                f"Utility={utility:+.3f}R | "
                f"Grade={grade.value} | "
                f"Penalties: U={uncertainty_penalty:.2f} "
                f"D={drawdown_penalty:.2f} "
                f"C={contradiction_penalty:.2f} "
                f"M={memory_penalty:.2f}"
            ),
        )
