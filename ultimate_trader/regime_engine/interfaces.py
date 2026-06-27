from abc import ABC, abstractmethod

from ultimate_trader.schemas.market import MarketRegimeAssessment, MarketSnapshot


class RegimeEngineInterface(ABC):
    @abstractmethod
    def assess_regime(
        self, snapshot: MarketSnapshot, context: dict
    ) -> MarketRegimeAssessment:
        ...
