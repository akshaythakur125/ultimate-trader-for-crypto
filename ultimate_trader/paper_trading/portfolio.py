from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.paper_trading.order import OrderFill, OrderSide


class PaperPosition(BaseModel):
    position_id: str
    symbol: str
    side: OrderSide
    entry_price: float
    quantity: float
    leverage: int = 1
    current_price: float = 0.0
    entry_time: datetime = Field(default_factory=lambda: datetime.utcnow())
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    correlation_id: Optional[str] = None
    entry_fills: list[OrderFill] = Field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.current_price == 0.0 or self.quantity > 0

    @property
    def margin(self) -> float:
        return (self.entry_price * self.quantity) / self.leverage

    @property
    def unrealized_pnl(self) -> float:
        if self.current_price == 0:
            return 0.0
        if self.side == OrderSide.BUY:
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * self.quantity

    @property
    def unrealized_pnl_percent(self) -> float:
        if self.margin == 0:
            return 0.0
        return (self.unrealized_pnl / self.margin) * 100

    @property
    def entry_fee(self) -> float:
        return sum(f.fee for f in self.entry_fills)


class ClosedTrade(BaseModel):
    trade_id: str
    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    fee: float
    holding_time_hours: float
    entry_time: datetime
    exit_time: datetime = Field(default_factory=lambda: datetime.utcnow())
    exit_reason: str = ""
    rr: float = 0.0
    correlation_id: Optional[str] = None

    @property
    def pnl_percent(self) -> float:
        cost = self.entry_price * self.quantity
        if cost == 0:
            return 0.0
        return (self.net_pnl / cost) * 100

    @property
    def was_profitable(self) -> bool:
        return self.gross_pnl > 0
