class ConfidenceUpdateResult:
    def __init__(
        self,
        confidence: float = 50.0,
        risk: float = 50.0,
        uncertainty: float = 50.0,
    ) -> None:
        self.confidence = round(confidence, 1)
        self.risk = round(risk, 1)
        self.uncertainty = round(uncertainty, 1)

    def __repr__(self) -> str:
        return (
            f"ConfidenceUpdateResult("
            f"confidence={self.confidence}, "
            f"risk={self.risk}, "
            f"uncertainty={self.uncertainty})"
        )


class ConfidenceUpdater:
    def __init__(self, baseline: float = 50.0) -> None:
        self.baseline = baseline

    def update(
        self,
        supporting_count: int = 0,
        contradicting_count: int = 0,
        missing_evidence_count: int = 0,
        uncertainty_score: float = 50.0,
        warning_count: int = 0,
    ) -> ConfidenceUpdateResult:
        confidence = self.baseline
        risk = 50.0
        uncertainty = uncertainty_score

        confidence += supporting_count * 8.0
        confidence -= contradicting_count * 12.0
        confidence -= missing_evidence_count * 5.0

        risk += contradicting_count * 8.0
        risk += warning_count * 6.0
        risk += missing_evidence_count * 4.0

        uncertainty_cap = 100.0 - uncertainty
        confidence = min(confidence, uncertainty_cap)

        confidence = max(0.0, min(100.0, confidence))
        risk = max(0.0, min(100.0, risk))
        uncertainty = max(0.0, min(100.0, uncertainty))

        return ConfidenceUpdateResult(
            confidence=confidence,
            risk=risk,
            uncertainty=uncertainty,
        )
