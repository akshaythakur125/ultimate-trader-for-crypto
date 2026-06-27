from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Kline(BaseModel):
    symbol: str
    interval: str
    open_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    close_time: datetime
    quote_volume: float
    trade_count: int


class Ticker(BaseModel):
    symbol: str
    last_price: float
    price_change_percent: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float


class OrderBookLevel(BaseModel):
    price: float
    quantity: float


class OrderBook(BaseModel):
    symbol: str
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    last_update_id: Optional[int] = None


class ExchangeSymbol(BaseModel):
    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    min_qty: float = 0.0
    max_qty: float = 0.0
    step_size: float = 0.0
    tick_size: float = 0.0
