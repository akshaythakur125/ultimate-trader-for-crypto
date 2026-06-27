from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.schemas.hypothesis import EvidenceBundle


class IntelligenceDecision(BaseModel):
    decision_id: str
    symbol: str
    timestamp: datetime
    bias: str
    long_probability: float = Field(ge=0.0, le=1.0)
    short_probability: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=100.0)
    risk_score: float = Field(ge=0.0, le=100.0)
    uncertainty_score: float = Field(ge=0.0, le=100.0)
    trade_quality_score: float = Field(ge=0.0, le=100.0)
    reasoning_summary: str
    evidence: Optional[EvidenceBundle] = None
    invalidation_level: Optional[float] = None
    requires_human_review: bool = False
