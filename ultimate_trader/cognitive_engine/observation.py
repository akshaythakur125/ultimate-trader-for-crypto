from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ObservationType(str, Enum):
    PRICE_ACTION = "PRICE_ACTION"
    VOLUME = "VOLUME"
    LIQUIDITY = "LIQUIDITY"
    ORDER_FLOW = "ORDER_FLOW"
    VOLATILITY = "VOLATILITY"
    FUNDING = "FUNDING"
    OPEN_INTEREST = "OPEN_INTEREST"
    REGIME = "REGIME"
    SENTIMENT = "SENTIMENT"
    RISK = "RISK"
    UNKNOWN = "UNKNOWN"


class Observation(BaseModel):
    observation_id: str
    symbol: str
    timeframe: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    observation_type: ObservationType
    description: str
    raw_features: dict = Field(default_factory=dict)
    source: str
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
