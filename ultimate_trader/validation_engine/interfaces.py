from abc import ABC, abstractmethod

from ultimate_trader.schemas.hypothesis import TradingHypothesis
from ultimate_trader.schemas.signal import SignalCandidate


class ValidationEngineInterface(ABC):
    @abstractmethod
    def validate_signal(
        self, signal: SignalCandidate, hypothesis: TradingHypothesis
    ) -> SignalCandidate:
        ...
