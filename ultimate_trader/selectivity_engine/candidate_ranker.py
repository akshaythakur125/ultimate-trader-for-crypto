from dataclasses import dataclass, field
from typing import Any, Optional


RANK_GRADES = ["A_PLUS", "A", "B", "C", "REJECT"]


@dataclass
class RankedCandidate:
    candidate_id: str
    symbol: str
    direction: str
    timestamp: Any
    rank_score: float = 0.0
    rank_grade: str = "REJECT"
    confluence_score: float = 0.0
    directional_confidence: float = 0.0
    conflict_score: float = 0.0
    reversal_risk_score: float = 0.0
    continuation_score: float = 0.0
    expected_value_r: float = 0.0
    rr_ratio: float = 0.0
    risk_score: float = 0.0
    target_realism_score: float = 0.0
    stop_quality_score: float = 0.0
    volatility_alignment: float = 0.0
    lsm_sweep_quality: float = 0.0
    orderflow_confirmation: float = 0.0
    microstructure_confirmation: float = 0.0
    reasons_for: list[str] = field(default_factory=list)
    reasons_against: list[str] = field(default_factory=list)


class CandidateRanker:
    def rank(self, candidate: Any, confluence_result: Any) -> RankedCandidate:
        rc = RankedCandidate(
            candidate_id=getattr(candidate, "candidate_id", "UNKNOWN"),
            symbol=getattr(candidate, "symbol", "UNKNOWN"),
            direction=getattr(candidate, "direction", "LONG"),
            timestamp=getattr(candidate, "timestamp", None),
        )

        confluence = confluence_result
        if confluence is None:
            rc.rank_grade = "REJECT"
            rc.reasons_against.append("No confluence result")
            return rc

        rc.confluence_score = getattr(confluence, "confluence_score", 0.0)
        rc.directional_confidence = getattr(confluence, "directional_confidence", 0.0)
        rc.conflict_score = getattr(confluence, "conflict_score", 0.0)
        rc.reversal_risk_score = getattr(confluence, "reversal_risk_score", 0.0)
        rc.continuation_score = getattr(confluence, "continuation_score", 0.0)

        rr = getattr(candidate, "target_price", 0.0) - getattr(candidate, "entry_price", 0.0)
        risk = abs(getattr(candidate, "entry_price", 0.0) - getattr(candidate, "stop_loss", 0.0))
        rc.rr_ratio = abs(rr / risk) if risk > 0 else 0.0

        rc.risk_score = min(100 - rc.confluence_score, 100) if rc.confluence_score > 0 else 50.0
        rc.expected_value_r = rc.rr_ratio * (rc.confluence_score / 100) - (1 - rc.confluence_score / 100)

        rc.target_realism_score = self._score_target_realism(rc.rr_ratio, rc.continuation_score)
        rc.stop_quality_score = self._score_stop_quality(rc.conflict_score, rc.reversal_risk_score)
        rc.volatility_alignment = self._score_volatility_alignment(rc.confluence_score, rc.reversal_risk_score)
        rc.lsm_sweep_quality = self._score_sweep_quality(confluence)
        rc.orderflow_confirmation = self._score_orderflow(confluence)
        rc.microstructure_confirmation = self._score_microstructure(confluence)

        rank_score = self._compute_rank_score(rc)

        rc.rank_score = round(rank_score, 1)
        rc.rank_grade = self._assign_grade(rank_score)
        rc.reasons_for = self._build_reasons_for(rc)
        rc.reasons_against = self._build_reasons_against(rc)

        return rc

    def _score_target_realism(self, rr: float, continuation: float) -> float:
        score = 0.0
        if 2.0 <= rr <= 5.0:
            score += 50.0
        elif rr >= 3.0:
            score += 30.0
        if continuation >= 50:
            score += 30.0
        elif continuation >= 30:
            score += 15.0
        if rr > 8.0:
            score -= 20.0
        return max(0, min(100, score))

    def _score_stop_quality(self, conflict: float, reversal_risk: float) -> float:
        score = 100.0
        if conflict >= 0.5:
            score -= 30.0
        if reversal_risk >= 60:
            score -= 25.0
        elif reversal_risk >= 40:
            score -= 10.0
        return max(0, score)

    def _score_volatility_alignment(self, confluence: float, reversal_risk: float) -> float:
        if confluence >= 60 and reversal_risk < 30:
            return 80.0
        if confluence >= 40 and reversal_risk < 50:
            return 60.0
        return 30.0

    def _score_sweep_quality(self, conf: Any) -> float:
        reasons = getattr(conf, "reasons_for", []) or []
        sweep_mentions = [r for r in reasons if "sweep" in r.lower() or "liquidity" in r.lower()]
        if not sweep_mentions:
            return 0.0
        return min(len(sweep_mentions) * 25, 100)

    def _score_orderflow(self, conf: Any) -> float:
        reasons = getattr(conf, "reasons_for", []) or []
        if any("order flow" in r.lower() for r in reasons):
            return 80.0
        if any("microstructure" in r.lower() for r in reasons):
            return 50.0
        return 0.0

    def _score_microstructure(self, conf: Any) -> float:
        reasons = getattr(conf, "reasons_for", []) or []
        if any("microstructure" in r.lower() for r in reasons):
            return 70.0
        return 0.0

    def _compute_rank_score(self, rc: RankedCandidate) -> float:
        score = 0.0

        score += rc.confluence_score * 0.25
        score += rc.directional_confidence * 100 * 0.15
        score += (1 - rc.conflict_score) * 100 * 0.12
        score += rc.continuation_score * 0.10
        score += (100 - rc.reversal_risk_score) * 0.08
        score += rc.target_realism_score * 0.08
        score += rc.stop_quality_score * 0.07
        score += rc.lsm_sweep_quality * 0.05
        score += rc.volatility_alignment * 0.05
        score += rc.orderflow_confirmation * 0.03
        score += rc.microstructure_confirmation * 0.02

        rr_bonus = min(rc.rr_ratio / 3.0, 2.0)
        score += rr_bonus * 5

        return max(0, min(100, score))

    def _assign_grade(self, score: float) -> str:
        if score >= 85:
            return "A_PLUS"
        if score >= 70:
            return "A"
        if score >= 55:
            return "B"
        if score >= 40:
            return "C"
        return "REJECT"

    def _build_reasons_for(self, rc: RankedCandidate) -> list[str]:
        reasons = []
        if rc.confluence_score >= 60:
            reasons.append(f"Strong confluence: {rc.confluence_score:.0f}")
        if rc.directional_confidence >= 0.6:
            reasons.append(f"Directional confidence: {rc.directional_confidence:.0%}")
        if rc.conflict_score < 0.3:
            reasons.append(f"Low conflict: {rc.conflict_score:.0%}")
        if rc.continuation_score >= 50:
            reasons.append(f"Continuation supported: {rc.continuation_score:.0f}")
        if rc.rr_ratio >= 3.0:
            reasons.append(f"Good RR: {rc.rr_ratio:.1f}")
        if rc.lsm_sweep_quality >= 50:
            reasons.append("LSM sweep confirmation")
        return reasons

    def _build_reasons_against(self, rc: RankedCandidate) -> list[str]:
        reasons = []
        if rc.confluence_score < 40:
            reasons.append(f"Low confluence: {rc.confluence_score:.0f}")
        if rc.directional_confidence < 0.5:
            reasons.append(f"Weak directional confidence: {rc.directional_confidence:.0%}")
        if rc.conflict_score >= 0.5:
            reasons.append(f"High conflict: {rc.conflict_score:.0%}")
        if rc.reversal_risk_score >= 50:
            reasons.append(f"High reversal risk: {rc.reversal_risk_score:.0f}")
        if rc.rr_ratio < 2.5:
            reasons.append(f"Low RR: {rc.rr_ratio:.1f}")
        if rc.target_realism_score < 40:
            reasons.append("Unrealistic target")
        if rc.stop_quality_score < 50:
            reasons.append("Poor stop placement")
        return reasons
