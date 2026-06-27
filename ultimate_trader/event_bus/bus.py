import logging
from collections import defaultdict
from typing import Optional

from ultimate_trader.event_bus.events import BaseEvent, EventType
from ultimate_trader.event_bus.handlers import EventHandler

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[Optional[EventType], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._subscribers[None].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event: BaseEvent) -> None:
        specific_handlers = list(self._subscribers.get(event.event_type, []))
        wildcard_handlers = list(self._subscribers.get(None, []))
        all_handlers = specific_handlers + wildcard_handlers

        for handler in all_handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Handler failed for event %s: %s",
                    event.event_type.value,
                    handler.__name__ if hasattr(handler, "__name__") else str(handler),
                )

    def publish_batch(self, events: list[BaseEvent]) -> None:
        for event in events:
            self.publish(event)

    def list_subscribers(self, event_type: Optional[EventType] = None) -> list[EventHandler]:
        if event_type is None:
            result = {}
            for et, handlers in self._subscribers.items():
                result[et.value if et else "WILDCARD"] = list(handlers)
            return result
        return list(self._subscribers.get(event_type, []))

    def clear_subscribers(self) -> None:
        self._subscribers.clear()
