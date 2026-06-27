from abc import ABC, abstractmethod
from typing import Optional

from ultimate_trader.schemas.hypothesis import TradingHypothesis


class HypothesisRegistryInterface(ABC):
    @abstractmethod
    def register(self, hypothesis: TradingHypothesis) -> str:
        ...

    @abstractmethod
    def get(self, hypothesis_id: str) -> Optional[TradingHypothesis]:
        ...

    @abstractmethod
    def list_active(self) -> list[TradingHypothesis]:
        ...

    @abstractmethod
    def update_status(
        self,
        hypothesis_id: str,
        status: str,
        rejection_reason: Optional[str] = None,
    ) -> None:
        ...
