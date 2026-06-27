from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DirectionBias(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalContext(BaseModel):
    context_id: str
    symbol: str
    exchange: str = ""
    timeframe: str
    validated_hypothesis_id: str
    hypothesis_name: str = ""
    direction_bias: DirectionBias
    current_price: float = 0.0
    market_regime: Optional[str] = None
    volatility_score: float = 0.0
    liquidity_score: float = 0.0
    manipulation_score: float = 0.0
    orderflow_score: float = 0.0
    confidence_score: float = 0.0
    risk_score: float = 0.0
    uncertainty_score: float = 0.0
    expected_value_r: float = 0.0
    validation_passed: bool = False
    memory_support_score: Optional[float] = None
    contradiction_score: Optional[float] = None
    no_trade_probability: Optional[float] = None
    notes: str = ""
