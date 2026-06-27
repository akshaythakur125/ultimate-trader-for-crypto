from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Candle(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class SwingType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    EQUAL_HIGH = "EQUAL_HIGH"
    EQUAL_LOW = "EQUAL_LOW"
    INTERNAL_HIGH = "INTERNAL_HIGH"
    INTERNAL_LOW = "INTERNAL_LOW"
    EXTERNAL_HIGH = "EXTERNAL_HIGH"
    EXTERNAL_LOW = "EXTERNAL_LOW"


class SwingPoint(BaseModel):
    price: float
    index: int
    swing_type: SwingType
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())


class LiquidityZone(BaseModel):
    zone_type: str  # BUY_SIDE / SELL_SIDE / STOP_CLUSTER
    price_min: float
    price_max: float
    is_swept: bool = False
    sweep_index: Optional[int] = None
    strength: float = 1.0
    created_at_index: int = 0
    label: str = ""


class Sweep(BaseModel):
    sweep_type: str  # BUY_SIDE_SWEEP / SELL_SIDE_SWEEP
    entry_price: float
    sweep_low: float
    sweep_high: float
    reclaim_price: Optional[float] = None
    has_reclaim: bool = False
    is_failed: bool = False
    has_displacement: bool = False
    index: int = 0
    description: str = ""


class StructureType(str, Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"
    MSS = "MSS"
    TREND_CONTINUATION = "TREND_CONTINUATION"
    STRUCTURE_FAILURE = "STRUCTURE_FAILURE"
    RANGE = "RANGE"
    COMPRESSION = "COMPRESSION"


class StructureEvent(BaseModel):
    structure_type: StructureType
    direction: str = ""  # BULLISH / BEARISH
    price: float = 0.0
    index: int = 0
    description: str = ""


class DirectionalBias(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class FVG(BaseModel):
    fvg_type: str = ""  # BULLISH_FVG / BEARISH_FVG
    gap_high: float = 0.0
    gap_low: float = 0.0
    gap_size: float = 0.0
    is_mitigated: bool = False
    is_filled: bool = False
    index: int = 0
    description: str = ""


class OrderBlock(BaseModel):
    ob_type: str = ""  # BULLISH_OB / BEARISH_OB / BREAKER_BLOCK / MITIGATION_BLOCK
    price_high: float = 0.0
    price_low: float = 0.0
    is_mitigated: bool = False
    is_invalidated: bool = False
    strength_score: float = 0.0
    index: int = 0
    description: str = ""


class PremiumDiscountState(BaseModel):
    dealing_range_high: float = 0.0
    dealing_range_low: float = 0.0
    equilibrium: float = 0.0
    premium_zone_high: float = 0.0
    premium_zone_low: float = 0.0
    discount_zone_high: float = 0.0
    discount_zone_low: float = 0.0
    optimal_entry_high: float = 0.0
    optimal_entry_low: float = 0.0
    current_price_zone: str = ""  # PREMIUM / DISCOUNT / EQUILIBRIUM


class Displacement(BaseModel):
    is_displaced: bool = False
    displacement_type: str = ""  # STRONG / WEAK / VOLUME_SUPPORTED / AFTER_SWEEP / FAKE
    candle_range: float = 0.0
    volume_ratio: float = 0.0
    direction: str = ""  # UP / DOWN
    index: int = 0
    description: str = ""


class ConfluenceResult(BaseModel):
    confluence_score: float = 0.0
    directional_bias: DirectionalBias = DirectionalBias.NEUTRAL
    directional_confidence: float = 0.0
    reversal_risk_score: float = 0.0
    continuation_score: float = 0.0
    conflict_score: float = 0.0
    reason_for_direction: str = ""
    trade_permission: str = "ALLOW"
    reasons_for: list[str] = Field(default_factory=list)
    reasons_against: list[str] = Field(default_factory=list)
    confluence_breakdown: dict[str, float] = Field(default_factory=dict)


class TradePermission(str, Enum):
    ALLOW = "ALLOW"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"
