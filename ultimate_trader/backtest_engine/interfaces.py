from abc import ABC, abstractmethod

from ultimate_trader.schemas.backtest import BacktestSummary
from ultimate_trader.schemas.hypothesis import TradingHypothesis


class BacktestEngineInterface(ABC):
    @abstractmethod
    async def run_backtest(
        self,
        hypothesis: TradingHypothesis,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> BacktestSummary:
        ...
