from abc import ABC, abstractmethod

from ultimate_trader.schemas.risk import RiskAssessment
from ultimate_trader.schemas.signal import SignalCandidate


class RiskEngineInterface(ABC):
    @abstractmethod
    def assess_risk(self, signal: SignalCandidate) -> RiskAssessment:
        ...

    @abstractmethod
    def enforce_drawdown_limits(self, current_drawdown: float) -> bool:
        ...
