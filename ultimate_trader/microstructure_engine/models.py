from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderBookLevel(BaseModel):
    price: float
    quantity: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)

    @property
    def best_bid(self) -> float:
        return max((b.price for b in self.bids), default=0.0)

    @property
    def best_ask(self) -> float:
        return min((a.price for a in self.asks), default=0.0)

    @property
    def mid_price(self) -> float:
        if self.best_bid > 0 and self.best_ask > 0:
            return (self.best_bid + self.best_ask) / 2.0
        return 0.0

    @property
    def spread(self) -> float:
        if self.best_bid > 0 and self.best_ask > 0:
            return self.best_ask - self.best_bid
        return 0.0

    @property
    def spread_bps(self) -> float:
        if self.mid_price > 0:
            return (self.spread / self.mid_price) * 10000
        return 0.0

    @property
    def bid_depth(self) -> float:
        return sum(b.quantity for b in self.bids)

    @property
    def ask_depth(self) -> float:
        return sum(a.quantity for a in self.asks)

    @property
    def depth_imbalance(self) -> float:
        total = self.bid_depth + self.ask_depth
        if total == 0:
            return 0.0
        return (self.bid_depth - self.ask_depth) / total

    def get_bid_depth_to_price(self, price_level: float) -> float:
        return sum(b.quantity for b in self.bids if b.price >= price_level)

    def get_ask_depth_to_price(self, price_level: float) -> float:
        return sum(a.quantity for a in self.asks if a.price <= price_level)


class SpreadState(str, Enum):
    NORMAL = "NORMAL"
    WIDE = "WIDE"
    UNSTABLE = "UNSTABLE"
    TRADE_BLOCKING = "TRADE_BLOCKING"


class DepthState(str, Enum):
    NORMAL = "NORMAL"
    THIN = "THIN"
    IMBALANCED = "IMBALANCED"
    CRITICAL = "CRITICAL"


class ImbalanceBias(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class AbsorptionState(str, Enum):
    NONE = "NONE"
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"


class SpoofingRiskLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExecutionRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TradePermission(str, Enum):
    ALLOW = "ALLOW"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"


class LiquidityVoid(BaseModel):
    zone_label: str
    price_above: float
    price_below: float
    depth_in_zone: float
    severity: str = "LOW"


class AbsorptionSignal(BaseModel):
    detected: bool
    absorption_type: str = ""
    level_price: float = 0.0
    strength: str = "LOW"
    description: str = ""


class SpoofingSignal(BaseModel):
    detected: bool
    risk_level: SpoofingRiskLevel = SpoofingRiskLevel.NONE
    reason: str = ""


class PriceImpactEstimate(BaseModel):
    expected_slippage_bps: float = 0.0
    position_too_large: bool = False
    execution_risk: ExecutionRisk = ExecutionRisk.LOW
    max_safe_order_quantity: float = 0.0
    reason: str = ""
