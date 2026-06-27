from abc import ABC, abstractmethod

from ultimate_trader.schemas.market import LiquidityAssessment, MarketSnapshot


class LiquidityEngineInterface(ABC):
    @abstractmethod
    def analyze_liquidity(
        self, snapshot: MarketSnapshot, context: dict
    ) -> LiquidityAssessment:
        ...
