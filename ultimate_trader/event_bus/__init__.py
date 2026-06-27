from typing import Any, Optional

from ultimate_trader.event_bus.bus import EventBus
from ultimate_trader.event_bus.event_store import EventStore
from ultimate_trader.event_bus.events import BaseEvent, EventType
from ultimate_trader.event_bus.handlers import EventHandler, EventHandlerProtocol

_default_bus: Optional[EventBus] = None
_default_store: Optional[EventStore] = None


def get_default_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def get_default_store() -> EventStore:
    global _default_store
    if _default_store is None:
        _default_store = EventStore()
    return _default_store


def publish_system_event(
    event_type: EventType,
    source_module: str,
    payload: dict[str, Any] = None,
    correlation_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
) -> BaseEvent:
    if payload is None:
        payload = {}
    event = BaseEvent(
        event_type=event_type,
        source_module=source_module,
        payload=payload,
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
    )
    bus = get_default_bus()
    store = get_default_store()
    bus.publish(event)
    store.save_event(event)
    return event


__all__ = [
    "EventBus",
    "EventStore",
    "BaseEvent",
    "EventType",
    "EventHandler",
    "EventHandlerProtocol",
    "get_default_bus",
    "get_default_store",
    "publish_system_event",
]
