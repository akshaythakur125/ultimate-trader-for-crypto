from abc import ABC, abstractmethod
from datetime import datetime

from ultimate_trader.schemas.learning import LearningReport


class LearningEngineInterface(ABC):
    @abstractmethod
    def generate_report(
        self, start: datetime, end: datetime
    ) -> LearningReport:
        ...
