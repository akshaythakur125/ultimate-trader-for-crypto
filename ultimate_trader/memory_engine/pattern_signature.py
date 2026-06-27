import uuid
from typing import Optional

from pydantic import BaseModel, Field


class PatternSignature(BaseModel):
    signature_id: str
    symbol: str
    timeframe: str
    regime_label: str
    liquidity_state: str
    orderflow_state: str
    volatility_state: str
    trend_state: str
    funding_state: Optional[str] = None
    open_interest_state: Optional[str] = None
    manipulation_risk_state: Optional[str] = None
    compression_state: Optional[str] = None
    feature_vector: dict[str, float] = Field(default_factory=dict)
