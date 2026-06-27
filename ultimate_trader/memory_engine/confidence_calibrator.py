from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.memory_engine.market_case import MarketCase, OutcomeLabel
from ultimate_trader.memory_engine.pattern_signature import PatternSignature


class ConfidenceCalibrationResult(BaseModel):
    original_confidence: float
    calibrated_confidence: float
    original_risk_score: float = 50.0
    calibrated_risk_score: float = 50.0
    memory_support_score: float = 50.0
    memory_warning_score: float = 0.0
    similar_cases_count: int = 0
    calibration_reason: str = ""
    insufficient_memory: bool = False


class ConfidenceCalibrator:
    def calibrate(
        self,
        base_confidence: float,
        current_signature: PatternSignature,
        similar_cases: list[MarketCase],
        min_memory_threshold: int = 3,
    ) -> ConfidenceCalibrationResult:
        confidence = base_confidence
        support_score = 50.0
        warning_score = 0.0
        risk_score = 50.0
        reasons: list[str] = []

        if len(similar_cases) < min_memory_threshold:
            confidence -= 10.0
            reasons.append(
                f"Insufficient memory ({len(similar_cases)} cases, "
                f"need {min_memory_threshold})"
            )
            return ConfidenceCalibrationResult(
                original_confidence=base_confidence,
                calibrated_confidence=max(0.0, confidence),
                original_risk_score=risk_score,
                calibrated_risk_score=risk_score + 5.0,
                memory_support_score=0.0,
                memory_warning_score=30.0,
                similar_cases_count=len(similar_cases),
                calibration_reason=" | ".join(reasons),
                insufficient_memory=True,
            )

        resolved = [
            c
            for c in similar_cases
            if c.outcome_label in (OutcomeLabel.WIN, OutcomeLabel.LOSS)
        ]
        if not resolved:
            confidence -= 5.0
            reasons.append("No resolved outcomes in similar cases")
        else:
            wins = sum(
                1 for c in resolved if c.outcome_label == OutcomeLabel.WIN
            )
            losses = sum(
                1 for c in resolved if c.outcome_label == OutcomeLabel.LOSS
            )
            win_rate = wins / len(resolved)
            support_score = win_rate * 100
            warning_score = (1 - win_rate) * 100

            total_rr = sum(
                c.realized_rr
                for c in resolved
                if c.realized_rr is not None
            )
            rr_count = sum(
                1 for c in resolved if c.realized_rr is not None
            )

            if win_rate > 0.6 and rr_count > 0:
                avg_rr = total_rr / rr_count
                if avg_rr > 2.0:
                    confidence += 15.0
                    reasons.append(
                        f"Strong historical support ({win_rate*100:.0f}% win rate, "
                        f"avg R:R {avg_rr:.1f})"
                    )
                elif avg_rr > 1.0:
                    confidence += 10.0
                    reasons.append(
                        f"Positive historical support ({win_rate*100:.0f}% win rate)"
                    )
                else:
                    confidence += 5.0
            elif win_rate > 0.4:
                reasons.append("Mixed historical outcomes")
            else:
                confidence -= 15.0
                reasons.append(
                    f"Poor historical outcomes ({win_rate*100:.0f}% win rate)"
                )

            adverse_excursions = [
                c.max_adverse_excursion
                for c in resolved
                if c.max_adverse_excursion is not None
            ]
            if adverse_excursions:
                avg_ae = sum(adverse_excursions) / len(adverse_excursions)
                if avg_ae > 3.0:
                    risk_score += 15.0
                    reasons.append(
                        f"High avg adverse excursion ({avg_ae:.1f})"
                    )
                elif avg_ae > 1.5:
                    risk_score += 5.0
                    reasons.append(
                        f"Moderate avg adverse excursion ({avg_ae:.1f})"
                    )

        calibrated_confidence = max(0.0, min(100.0, confidence))

        return ConfidenceCalibrationResult(
            original_confidence=base_confidence,
            calibrated_confidence=round(calibrated_confidence, 1),
            original_risk_score=50.0,
            calibrated_risk_score=round(min(100.0, risk_score), 1),
            memory_support_score=round(support_score, 1),
            memory_warning_score=round(warning_score, 1),
            similar_cases_count=len(similar_cases),
            calibration_reason=" | ".join(reasons) if reasons else "No adjustment needed",
            insufficient_memory=False,
        )
