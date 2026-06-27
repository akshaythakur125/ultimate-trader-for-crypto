from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.hypothesis_reasoning import AlternativeHypothesis
from ultimate_trader.cognitive_engine.observation import Observation, ObservationType


class EvidenceType(str, Enum):
    CONFIRMATION = "CONFIRMATION"
    CONTRADICTION = "CONTRADICTION"
    WARNING = "WARNING"
    MISSING = "MISSING"
    NEUTRAL = "NEUTRAL"


class EvidenceItem(BaseModel):
    evidence_id: str
    description: str
    evidence_type: EvidenceType
    supports: Optional[str] = None
    contradicts: Optional[str] = None
    strength_score: float = Field(default=0.5, ge=0.0, le=1.0)
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_observation_id: Optional[str] = None


class EvidenceEvaluator:
    def score_evidence_strength(self, item: EvidenceItem) -> float:
        raw = item.strength_score * item.reliability_score
        if item.evidence_type == EvidenceType.CONFIRMATION:
            return min(raw * 1.2, 1.0)
        if item.evidence_type == EvidenceType.CONTRADICTION:
            return min(raw * 1.5, 1.0)
        if item.evidence_type == EvidenceType.WARNING:
            return min(raw * 1.1, 1.0)
        return raw

    def separate_supporting_contradicting(
        self,
        items: list[EvidenceItem],
        hypothesis_id: str,
    ) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
        supporting: list[EvidenceItem] = []
        contradicting: list[EvidenceItem] = []
        for item in items:
            if item.supports == hypothesis_id:
                supporting.append(item)
            elif item.contradicts == hypothesis_id:
                contradicting.append(item)
            elif item.supports is None and item.contradicts is None:
                if item.evidence_type == EvidenceType.CONFIRMATION:
                    supporting.append(item)
                elif item.evidence_type == EvidenceType.CONTRADICTION:
                    contradicting.append(item)
        return supporting, contradicting

    def detect_missing_critical_evidence(
        self,
        hypothesis: AlternativeHypothesis,
        available: list[EvidenceItem],
    ) -> list[str]:
        required = set(hypothesis.required_evidence)
        available_desc = {e.description.lower() for e in available}
        missing: list[str] = []
        for req in required:
            if req.lower() not in available_desc:
                missing.append(req)
        return missing

    def assess_missing_evidence(
        self,
        observations: list[Observation],
        hypothesis: AlternativeHypothesis,
    ) -> list[str]:
        missing: list[str] = []
        observed_types = {o.observation_type for o in observations}

        if hypothesis.direction_bias in ("LONG", "SHORT"):
            if ObservationType.ORDER_FLOW not in observed_types:
                missing.append("order_flow_confirmation")
            if ObservationType.VOLUME not in observed_types:
                missing.append("volume_confirmation")
            if ObservationType.LIQUIDITY not in observed_types:
                missing.append("liquidity_assessment")

        if hypothesis.direction_bias == "NO_TRADE":
            if ObservationType.REGIME not in observed_types:
                missing.append("regime_assessment")

        return missing

    def build_evidence_items(
        self,
        observations: list[Observation],
        hypothesis: AlternativeHypothesis,
    ) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for obs in observations:
            if obs.observation_id in hypothesis.supporting_observations:
                items.append(
                    EvidenceItem(
                        evidence_id=f"EV-{obs.observation_id}",
                        description=f"Observation {obs.observation_id} supports hypothesis",
                        evidence_type=EvidenceType.CONFIRMATION,
                        supports=hypothesis.hypothesis_id,
                        strength_score=obs.reliability_score,
                        reliability_score=obs.reliability_score,
                        source_observation_id=obs.observation_id,
                    )
                )
            elif obs.observation_id in hypothesis.contradicting_observations:
                items.append(
                    EvidenceItem(
                        evidence_id=f"EV-{obs.observation_id}",
                        description=f"Observation {obs.observation_id} contradicts hypothesis",
                        evidence_type=EvidenceType.CONTRADICTION,
                        contradicts=hypothesis.hypothesis_id,
                        strength_score=obs.reliability_score,
                        reliability_score=obs.reliability_score,
                        source_observation_id=obs.observation_id,
                    )
                )
        return items
