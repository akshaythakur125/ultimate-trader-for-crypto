from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    EXPIRY = "EXPIRY"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeDiagnostics(BaseModel):
    trade_id: str
    symbol: str
    direction: TradeDirection
    signal_time: datetime
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    exit_price: float = 0.0
    exit_reason: ExitReason = ExitReason.UNKNOWN
    net_r: float = 0.0
    gross_r: float = 0.0
    fees_r: float = 0.0
    slippage_r: float = 0.0
    holding_candles: int = 0
    candles_until_exit: int = 0
    max_favorable_excursion_r: float = 0.0
    max_adverse_excursion_r: float = 0.0
    entry_to_stop_distance_percent: float = 0.0
    entry_to_target_distance_percent: float = 0.0
    rr_ratio: float = 0.0
    signal_quality_grade: str = "NONE"
    confidence_score: float = 0.0
    filters_passed: list[str] = Field(default_factory=list)
    filters_failed: list[str] = Field(default_factory=list)
    directional_components: dict[str, float] = Field(default_factory=dict)
    directional_vote: str = ""
    conflict_severity: str = "NONE"

    def holding_time_minutes(self) -> float:
        if self.entry_time and self.exit_time:
            return (self.exit_time - self.entry_time).total_seconds() / 60.0
        return 0.0

    def is_winner(self) -> bool:
        return self.net_r > 0

    def is_loser(self) -> bool:
        return self.net_r <= 0

    def max_mfe_percent(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.direction == TradeDirection.LONG:
            return ((self.max_favorable_excursion_r * abs(self.entry_price - self.stop_loss)) / self.entry_price) * 100
        return ((self.max_favorable_excursion_r * abs(self.entry_price - self.stop_loss)) / self.entry_price) * 100

    def max_mae_percent(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.direction == TradeDirection.LONG:
            return ((self.max_adverse_excursion_r * abs(self.entry_price - self.stop_loss)) / self.entry_price) * 100
        return ((self.max_adverse_excursion_r * abs(self.entry_price - self.stop_loss)) / self.entry_price) * 100
