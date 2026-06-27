from typing import Optional

from pydantic import BaseModel, Field


class EvidenceLikelihood(BaseModel):
    evidence_id: str
    evidence_description: str
    target_belief_id: str
    likelihood_if_belief_true: float
    likelihood_if_belief_false: float
    reliability_score: float = 0.5
    evidence_weight: float = 1.0
    notes: str = ""
