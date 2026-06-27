from abc import ABC, abstractmethod

from ultimate_trader.schemas.market import MarketSnapshot


class PerceptionEngineInterface(ABC):
    @abstractmethod
    def process_snapshot(self, snapshot: MarketSnapshot) -> dict:
        ...
