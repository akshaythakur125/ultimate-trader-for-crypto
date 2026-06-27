from abc import ABC, abstractmethod


class AlertEngineInterface(ABC):
    @abstractmethod
    async def send_alert(self, message: str, level: str = "info") -> bool:
        ...
