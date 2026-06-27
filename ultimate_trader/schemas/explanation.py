from pydantic import BaseModel, Field


class SignalExplanation(BaseModel):
    signal_id: str
    core_reason: str
    confirmations: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    invalidation: str
    risk_notes: list[str] = Field(default_factory=list)
    why_trade_is_allowed: str
    what_would_cancel_trade: str
