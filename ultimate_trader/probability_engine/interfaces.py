from abc import ABC, abstractmethod

from ultimate_trader.schemas.decision import IntelligenceDecision
from ultimate_trader.schemas.hypothesis import EvidenceBundle


class ProbabilityEngineInterface(ABC):
    @abstractmethod
    def evaluate_probability(
        self, evidence: EvidenceBundle
    ) -> IntelligenceDecision:
        ...
