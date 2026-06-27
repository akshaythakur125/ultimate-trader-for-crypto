from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.core.constants import HypothesisStatus


class EvidenceBundle(BaseModel):
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class TradingHypothesis(BaseModel):
    hypothesis_id: str
    name: str
    description: str
    edge_theory: str
    expected_market_regime: str
    required_liquidity_condition: str
    required_orderflow_condition: str
    expected_holding_time_hours: float
    minimum_rr: float = Field(ge=0.0)
    preferred_rr: float = Field(ge=0.0)
    entry_logic_description: str
    invalidation_logic_description: str
    expected_failure_conditions: str
    status: HypothesisStatus = HypothesisStatus.DRAFT
    rejection_reason: Optional[str] = None
