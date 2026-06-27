from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AggressorSide(str, Enum):
    BUYER = "BUYER"
    SELLER = "SELLER"
    UNKNOWN = "UNKNOWN"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class TradePrint(BaseModel):
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())
    price: float
    quantity: float
    side: TradeSide = TradeSide.UNKNOWN
    aggressor_side: AggressorSide = AggressorSide.UNKNOWN
    trade_value: float = 0.0
    exchange: str = ""
    trade_id: Optional[str] = None


class FlowWindow(BaseModel):
    symbol: str
    timeframe_seconds: int = 60
    start_time: datetime = Field(default_factory=lambda: datetime.utcnow())
    end_time: datetime = Field(default_factory=lambda: datetime.utcnow())
    trades: list[TradePrint] = Field(default_factory=list)
    total_buy_volume: float = 0.0
    total_sell_volume: float = 0.0
    buy_sell_delta: float = 0.0
    cumulative_delta: float = 0.0
    total_trade_value: float = 0.0
    average_trade_size: float = 0.0
    large_trade_count: int = 0
    trade_count: int = 0


class AggressionBias(str, Enum):
    BUYER_AGGRESSION = "BUYER_AGGRESSION"
    SELLER_AGGRESSION = "SELLER_AGGRESSION"
    BALANCED = "BALANCED"
    UNKNOWN = "UNKNOWN"


class AbsorptionState(str, Enum):
    BUYING_ABSORBED = "BUYING_ABSORBED"
    SELLING_ABSORBED = "SELLING_ABSORBED"
    NO_ABSORPTION = "NO_ABSORPTION"
    UNKNOWN = "UNKNOWN"


class ExhaustionState(str, Enum):
    BUYER_EXHAUSTION = "BUYER_EXHAUSTION"
    SELLER_EXHAUSTION = "SELLER_EXHAUSTION"
    NO_EXHAUSTION = "NO_EXHAUSTION"
    UNKNOWN = "UNKNOWN"


class IcebergSuspicion(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    NONE = "NONE"


class DeltaDivergenceType(str, Enum):
    BULLISH_DIVERGENCE = "BULLISH_DIVERGENCE"
    BEARISH_DIVERGENCE = "BEARISH_DIVERGENCE"
    NO_DIVERGENCE = "NO_DIVERGENCE"
    UNKNOWN = "UNKNOWN"


class TrapRisk(str, Enum):
    LONG_TRAP_RISK = "LONG_TRAP_RISK"
    SHORT_TRAP_RISK = "SHORT_TRAP_RISK"
    LOW_TRAP_RISK = "LOW_TRAP_RISK"
    UNKNOWN = "UNKNOWN"


class TrapAction(str, Enum):
    WAIT = "WAIT"
    CAUTION = "CAUTION"
    BLOCK_TRADE = "BLOCK_TRADE"
    COLLECT_MORE_DATA = "COLLECT_MORE_DATA"


class OrderFlowState(BaseModel):
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())
    aggression_bias: AggressionBias = AggressionBias.UNKNOWN
    absorption_state: AbsorptionState = AbsorptionState.UNKNOWN
    exhaustion_state: ExhaustionState = ExhaustionState.UNKNOWN
    iceberg_suspicion: IcebergSuspicion = IcebergSuspicion.NONE
    delta_divergence: DeltaDivergenceType = DeltaDivergenceType.UNKNOWN
    trap_risk: TrapRisk = TrapRisk.UNKNOWN
    flow_momentum_score: float = 0.0
    institutional_activity_score: float = 0.0
    confidence_score: float = 0.0
    warning_flags: list[str] = Field(default_factory=list)
