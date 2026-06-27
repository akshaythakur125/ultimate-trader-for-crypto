from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    EXPIRY = "EXPIRY"
    MAX_HOLDING_TIME = "MAX_HOLDING_TIME"
    MANUAL = "MANUAL"


class ReplayConclusion(str, Enum):
    EDGE_DETECTED = "EDGE_DETECTED"
    NO_EDGE = "NO_EDGE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NEEDS_MORE_TESTING = "NEEDS_MORE_TESTING"


class HistoricalCandle(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class TradePlan(BaseModel):
    plan_id: str
    symbol: str
    direction: TradeDirection
    signal_time: datetime
    entry_zone_high: float
    entry_zone_low: float
    stop_loss: float
    target_price: float
    expiry_candles: int = 20
    max_holding_candles: int = 40
    source_hypothesis: Optional[str] = None
    signal_quality_grade: Optional[str] = None
    plan_reason: str = ""


class ReplayTrade(BaseModel):
    trade_id: str
    symbol: str
    direction: TradeDirection
    signal_time: datetime
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    gross_r: float = 0.0
    fees_r: float = 0.0
    slippage_r: float = 0.0
    funding_r: float = 0.0
    net_r: float = 0.0
    exit_reason: Optional[ExitReason] = None
    holding_candles: int = 0
    source_hypothesis: Optional[str] = None
    signal_quality_grade: Optional[str] = None


class ReplayConfig(BaseModel):
    confluence_score_threshold: float = 30.0
    min_rr: float = 3.0
    max_risk_score: float = 50.0
    min_confidence_score: float = 40.0
    max_uncertainty_score: float = 40.0
    stop_distance_multiplier: float = 1.0
    target_rr: float = 3.0
    warmup_candles: int = 50
    taker_fee_percent: float = 0.04
    maker_fee_percent: float = 0.02
    slippage_percent: float = 0.02
    funding_per_candle_percent: float = 0.001
