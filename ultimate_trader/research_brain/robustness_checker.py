import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.research_brain.hypothesis_generator import (
    ResearchHypothesis,
)


class RobustnessCheck(BaseModel):
    robustness_score: float
    score_id: str
    hypothesis_id: str
    checks_performed: list[str] = Field(default_factory=list)
    checks_passed: int = 0
    checks_failed: int = 0
    failure_details: list[str] = Field(default_factory=list)
    summary: str = ""


class RobustnessChecker:
    CHECKS = [
        "evidence_completeness",
        "falsifiability",
        "regime_specificity",
        "failure_mode_awareness",
        "rr_reasonableness",
        "supporting_evidence_exists",
    ]

    def check(self, hypothesis: ResearchHypothesis) -> RobustnessCheck:
        checks_performed = []
        passed = 0
        failed = 0
        failures = []

        if "evidence_completeness" in self.CHECKS:
            checks_performed.append("evidence_completeness")
            if hypothesis.required_evidence:
                passed += 1
            else:
                failed += 1
                failures.append("No required evidence defined")

        if "falsifiability" in self.CHECKS:
            checks_performed.append("falsifiability")
            if hypothesis.invalidating_evidence:
                passed += 1
            else:
                failed += 1
                failures.append("Hypothesis is not falsifiable")

        if "regime_specificity" in self.CHECKS:
            checks_performed.append("regime_specificity")
            if hypothesis.regime_dependency and hypothesis.regime_dependency != "any":
                passed += 1
            else:
                failed += 1
                failures.append("No specific regime dependency")

        if "failure_mode_awareness" in self.CHECKS:
            checks_performed.append("failure_mode_awareness")
            if hypothesis.expected_failure_modes:
                passed += 1
            else:
                failed += 1
                failures.append("No failure modes identified")

        if "rr_reasonableness" in self.CHECKS:
            checks_performed.append("rr_reasonableness")
            if 0 < hypothesis.expected_rr <= 10:
                passed += 1
            else:
                failed += 1
                failures.append(f"Unreasonable expected RR: {hypothesis.expected_rr}")

        if "supporting_evidence_exists" in self.CHECKS:
            checks_performed.append("supporting_evidence_exists")
            if hypothesis.supporting_evidence:
                passed += 1
            else:
                failed += 1
                failures.append("No supporting evidence yet")

        score = (passed / max(len(self.CHECKS), 1)) * 100.0

        return RobustnessCheck(
            robustness_score=score,
            score_id=f"RC-{uuid.uuid4().hex[:8].upper()}",
            hypothesis_id=hypothesis.research_id,
            checks_performed=checks_performed,
            checks_passed=passed,
            checks_failed=failed,
            failure_details=failures,
            summary=f"{passed}/{len(self.CHECKS)} checks passed ({score:.0f}%)",
        )
