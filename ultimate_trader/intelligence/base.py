from pydantic import BaseModel, Field


class ReasoningTrace(BaseModel):
    input_summary: str
    assumptions: list[str] = Field(default_factory=list)
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    conclusion: str


class ConfidenceAssessment(BaseModel):
    confidence_score: float = Field(ge=0.0, le=100.0)
    risk_score: float = Field(ge=0.0, le=100.0)
    uncertainty_score: float = Field(ge=0.0, le=100.0)
    confidence_reason: str
    risk_reason: str
    uncertainty_reason: str
