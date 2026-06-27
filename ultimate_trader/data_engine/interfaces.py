from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator, Optional

from ultimate_trader.schemas.market import MarketSnapshot


class DataProviderInterface(ABC):
    @abstractmethod
    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[MarketSnapshot]:
        ...

    @abstractmethod
    async def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        ...

    @abstractmethod
    async def fetch_open_interest(self, symbol: str) -> Optional[float]:
        ...

    @abstractmethod
    async def fetch_orderbook(self, symbol: str, depth: int = 10) -> dict:
        ...

    @abstractmethod
    async def stream_ticks(self, symbol: str) -> AsyncIterator[dict]:
        ...
