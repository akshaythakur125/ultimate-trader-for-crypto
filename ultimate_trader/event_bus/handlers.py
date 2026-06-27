from typing import Callable, Protocol

from ultimate_trader.event_bus.events import BaseEvent

EventHandler = Callable[[BaseEvent], None]


class EventHandlerProtocol(Protocol):
    def __call__(self, event: BaseEvent) -> None:
        ...
