from abc import ABC, abstractmethod

from ultimate_trader.schemas.signal import SignalCandidate


class ExecutionEngineInterface(ABC):
    @abstractmethod
    async def execute(self, signal: SignalCandidate) -> bool:
        ...

    @abstractmethod
    async def cancel(self, signal_id: str) -> bool:
        ...
