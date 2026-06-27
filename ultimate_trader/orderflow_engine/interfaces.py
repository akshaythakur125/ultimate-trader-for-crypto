from abc import ABC, abstractmethod

from ultimate_trader.schemas.market import MarketSnapshot, OrderFlowAssessment


class OrderFlowEngineInterface(ABC):
    @abstractmethod
    def analyze_orderflow(
        self, snapshot: MarketSnapshot, context: dict
    ) -> OrderFlowAssessment:
        ...
