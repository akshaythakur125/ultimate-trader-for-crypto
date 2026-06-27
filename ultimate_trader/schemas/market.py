from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MarketSnapshot(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    spread: Optional[float] = None
    volatility: Optional[float] = None
    orderbook_imbalance: Optional[float] = None
    liquidation_intensity: Optional[float] = None


class MarketRegimeAssessment(BaseModel):
    symbol: str
    timeframe: str
    regime_label: str
    trend_strength: float = Field(ge=0.0, le=1.0)
    volatility_state: str
    compression_score: float = Field(ge=0.0, le=1.0)
    manipulation_risk: float = Field(ge=0.0, le=1.0)
    no_trade_reason: Optional[str] = None


class LiquidityAssessment(BaseModel):
    symbol: str
    equal_highs_detected: bool = False
    equal_lows_detected: bool = False
    sweep_detected: bool = False
    fakeout_detected: bool = False
    liquidity_bias: Optional[str] = None
    key_liquidity_levels: list[float] = Field(default_factory=list)
    manipulation_score: float = Field(default=0.0, ge=0.0, le=1.0)


class OrderFlowAssessment(BaseModel):
    symbol: str
    orderflow_bias: Optional[str] = None
    volume_expansion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    funding_bias: Optional[str] = None
    open_interest_signal: Optional[str] = None
    orderbook_imbalance: Optional[float] = None
    liquidation_pressure: Optional[float] = None
    confirmation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    warning_flags: list[str] = Field(default_factory=list)
