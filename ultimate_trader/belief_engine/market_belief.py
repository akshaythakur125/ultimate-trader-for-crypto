from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DirectionBias(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"


class BeliefStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WEAK = "WEAK"
    REJECTED = "REJECTED"


class MarketBelief(BaseModel):
    belief_id: str
    name: str
    description: str = ""
    direction_bias: DirectionBias
    prior_probability: float
    posterior_probability: Optional[float] = None
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    expected_rr_if_correct: float = 0.0
    expected_loss_r_if_wrong: float = 0.0
    uncertainty_score: float = 50.0
    status: BeliefStatus = BeliefStatus.ACTIVE
