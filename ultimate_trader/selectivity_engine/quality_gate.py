from dataclasses import dataclass, field
from typing import Optional

from ultimate_trader.selectivity_engine.candidate_ranker import RankedCandidate


@dataclass
class QualityGateConfig:
    min_confluence_score: float = 50.0
    min_directional_confidence: float = 0.55
    max_conflict_score: float = 0.4
    max_reversal_risk_score: float = 50.0
    max_risk_score: float = 40.0
    min_rr: float = 3.0
    allowed_grades: set[str] = field(default_factory=lambda: {"A_PLUS", "A"})


@dataclass
class QualityGateResult:
    passed: bool = False
    rejection_reason: str = ""
    rejection_category: str = ""


class QualityGate:
    def __init__(self, config: Optional[QualityGateConfig] = None):
        self._config = config or QualityGateConfig()

    @property
    def config(self) -> QualityGateConfig:
        return self._config

    def evaluate(self, rc: RankedCandidate) -> QualityGateResult:
        result = QualityGateResult()

        if rc.rank_grade not in self._config.allowed_grades:
            result.rejection_reason = f"Rank grade {rc.rank_grade} not in allowed set {self._config.allowed_grades}"
            result.rejection_category = "low_rank"
            return result

        if rc.confluence_score < self._config.min_confluence_score:
            result.rejection_reason = f"Confluence {rc.confluence_score:.0f} < {self._config.min_confluence_score}"
            result.rejection_category = "confluence"
            return result

        if rc.directional_confidence < self._config.min_directional_confidence:
            result.rejection_reason = f"Directional confidence {rc.directional_confidence:.0%} < {self._config.min_directional_confidence:.0%}"
            result.rejection_category = "directional_confidence"
            return result

        if rc.conflict_score > self._config.max_conflict_score:
            result.rejection_reason = f"Conflict {rc.conflict_score:.0%} > {self._config.max_conflict_score:.0%}"
            result.rejection_category = "conflict"
            return result

        if rc.reversal_risk_score > self._config.max_reversal_risk_score:
            result.rejection_reason = f"Reversal risk {rc.reversal_risk_score:.0f} > {self._config.max_reversal_risk_score:.0f}"
            result.rejection_category = "reversal_risk"
            return result

        if rc.risk_score > self._config.max_risk_score:
            result.rejection_reason = f"Risk score {rc.risk_score:.0f} > {self._config.max_risk_score:.0f}"
            result.rejection_category = "risk"
            return result

        if rc.rr_ratio < self._config.min_rr:
            result.rejection_reason = f"RR {rc.rr_ratio:.1f} < {self._config.min_rr:.0f}"
            result.rejection_category = "rr"
            return result

        result.passed = True
        return result
