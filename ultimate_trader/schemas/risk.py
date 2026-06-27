from typing import Optional

from pydantic import BaseModel, Field


class RiskAssessment(BaseModel):
    symbol: str
    max_daily_drawdown_percent: float
    current_daily_drawdown_percent: float = 0.0
    position_risk_score: float = Field(ge=0.0, le=100.0)
    capital_at_risk_percent: float = Field(ge=0.0, le=100.0)
    risk_notes: list[str] = Field(default_factory=list)
    trading_locked: bool = False
    lock_reason: Optional[str] = None
