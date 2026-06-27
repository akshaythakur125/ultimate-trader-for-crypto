from typing import Optional

from pydantic import BaseModel


class ProbabilityCalibrationResult(BaseModel):
    raw_probability: float
    calibrated_probability: float
    calibration_adjustment: float
    calibration_reason: str = ""
    sufficient_sample_size: bool = True


class ProbabilityCalibrator:
    def calibrate(
        self,
        raw_probability: float,
        historical_win_rate: Optional[float] = None,
        similar_cases_count: Optional[int] = None,
        historical_expectancy: Optional[float] = None,
        memory_support_score: Optional[float] = None,
        memory_warning_score: Optional[float] = None,
        min_sample: int = 10,
    ) -> ProbabilityCalibrationResult:
        calibrated = raw_probability
        reasons: list[str] = []

        sample_size = similar_cases_count or 0
        sufficient = sample_size >= min_sample

        if not sufficient:
            reduction = (min_sample - sample_size) / min_sample * 0.05
            calibrated -= reduction
            reasons.append(
                f"Insufficient sample ({sample_size}/{min_sample}): "
                f"reduced by {reduction:.1%}"
            )

        if historical_win_rate is not None and historical_win_rate > 0:
            if raw_probability > historical_win_rate + 0.1:
                pull = (raw_probability - historical_win_rate) * 0.3
                calibrated -= pull
                reasons.append(
                    f"Pulled toward historical win rate ({historical_win_rate:.1%})"
                )

        if historical_expectancy is not None and historical_expectancy < 0:
            calibrated -= 0.05
            reasons.append("Historical expectancy is negative")

        if memory_warning_score is not None and memory_warning_score > 50:
            reduction = (memory_warning_score - 50) / 100 * 0.05
            calibrated -= reduction
            reasons.append(f"Memory warning score ({memory_warning_score:.0f})")

        if memory_support_score is not None and sufficient:
            if memory_support_score > 70:
                calibrated += 0.03
                reasons.append("Strong memory support")
            elif memory_support_score < 30:
                calibrated -= 0.03
                reasons.append("Low memory support")

        calibrated = max(0.01, min(0.99, calibrated))
        adjustment = calibrated - raw_probability

        return ProbabilityCalibrationResult(
            raw_probability=raw_probability,
            calibrated_probability=round(calibrated, 4),
            calibration_adjustment=round(adjustment, 4),
            calibration_reason=" | ".join(reasons) if reasons else "No adjustment needed",
            sufficient_sample_size=sufficient,
        )
