import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from ultimate_trader.event_bus.events import BaseEvent, EventType


class EventStore:
    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = os.path.join(
                str(Path.home()),
                ".ultimate_trader",
                "event_store",
                "events.json",
            )
        self._storage_path = storage_path
        self._ensure_storage()
        self._events: dict[str, dict] = {}
        self._load()

    def _ensure_storage(self) -> None:
        path = Path(self._storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("{}", encoding="utf-8")

    def _load(self) -> None:
        try:
            data = json.loads(Path(self._storage_path).read_text(encoding="utf-8"))
            self._events = data
        except (json.JSONDecodeError, FileNotFoundError):
            self._events = {}

    def _save(self) -> None:
        Path(self._storage_path).write_text(
            json.dumps(self._events, indent=2, default=str),
            encoding="utf-8",
        )

    def save_event(self, event: BaseEvent) -> None:
        self._events[event.event_id] = event.model_dump(mode="json")
        self._save()

    def get_event(self, event_id: str) -> Optional[BaseEvent]:
        raw = self._events.get(event_id)
        if raw is None:
            return None
        raw["event_type"] = EventType(raw["event_type"])
        if raw.get("timestamp"):
            raw["timestamp"] = datetime.fromisoformat(raw["timestamp"])
        return BaseEvent(**raw)

    def list_events(self) -> list[BaseEvent]:
        result = []
        for eid in sorted(self._events.keys(), reverse=True):
            event = self.get_event(eid)
            if event:
                result.append(event)
        return result

    def list_events_by_type(self, event_type: EventType) -> list[BaseEvent]:
        return [e for e in self.list_events() if e.event_type == event_type]

    def list_events_by_correlation_id(self, correlation_id: str) -> list[BaseEvent]:
        return [e for e in self.list_events() if e.correlation_id == correlation_id]

    def clear_events(self) -> None:
        self._events.clear()
        self._save()

    @property
    def count(self) -> int:
        return len(self._events)
