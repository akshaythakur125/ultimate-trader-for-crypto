from typing import Optional

from pydantic import BaseModel, Field


class DecisionThresholdResult(BaseModel):
    mathematically_acceptable: bool = False
    failed_thresholds: list[str] = Field(default_factory=list)
    passed_thresholds: list[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None
    threshold_summary: str = ""


class DecisionThresholds:
    def evaluate(
        self,
        expected_value_r: float,
        utility_grade: str,
        no_trade_probability: float,
        uncertainty_score: float,
        estimated_win_probability: float,
        required_win_rate: float,
        max_uncertainty: float = 70.0,
        max_no_trade: float = 0.5,
        min_utility_grade: str = "MARGINAL",
    ) -> DecisionThresholdResult:
        passed: list[str] = []
        failed: list[str] = []

        if expected_value_r > 0:
            passed.append(f"Positive EV ({expected_value_r:+.3f}R)")
        else:
            failed.append(f"Non-positive EV ({expected_value_r:+.3f}R)")

        grades = ["EXCELLENT", "GOOD", "MARGINAL", "BAD", "NO_TRADE"]
        min_idx = grades.index(min_utility_grade) if min_utility_grade in grades else 2
        actual_idx = grades.index(utility_grade) if utility_grade in grades else 4

        if actual_idx <= min_idx:
            passed.append(f"Utility grade {utility_grade} >= {min_utility_grade}")
        else:
            failed.append(f"Utility grade {utility_grade} below {min_utility_grade}")

        if no_trade_probability < max_no_trade:
            passed.append(
                f"No-trade probability {no_trade_probability:.1%} < {max_no_trade:.0%}"
            )
        else:
            failed.append(
                f"No-trade probability {no_trade_probability:.1%} >= {max_no_trade:.0%}"
            )

        if uncertainty_score < max_uncertainty:
            passed.append(
                f"Uncertainty {uncertainty_score:.0f} < {max_uncertainty:.0f}"
            )
        else:
            failed.append(
                f"Uncertainty {uncertainty_score:.0f} >= {max_uncertainty:.0f}"
            )

        if estimated_win_probability > required_win_rate:
            passed.append(
                f"Win prob {estimated_win_probability:.1%} > "
                f"breakeven {required_win_rate:.1%}"
            )
        else:
            failed.append(
                f"Win prob {estimated_win_probability:.1%} <= "
                f"breakeven {required_win_rate:.1%}"
            )

        acceptable = len(failed) == 0

        return DecisionThresholdResult(
            mathematically_acceptable=acceptable,
            failed_thresholds=failed,
            passed_thresholds=passed,
            rejection_reason="; ".join(failed) if failed else None,
            threshold_summary=(
                f"{'ACCEPTED' if acceptable else 'REJECTED'}: "
                f"{len(passed)} passed, {len(failed)} failed"
            ),
        )
