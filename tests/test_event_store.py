import os
import tempfile

import pytest

from ultimate_trader.event_bus import EventStore, EventType
from ultimate_trader.event_bus.events import BaseEvent


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".json")
    es = EventStore(storage_path=tmp)
    yield es
    if os.path.exists(tmp):
        os.remove(tmp)


class TestEventStore:
    def test_save_and_get_event(self, store):
        event = BaseEvent(
            event_type=EventType.HYPOTHESIS_GENERATED,
            source_module="test",
        )
        store.save_event(event)
        retrieved = store.get_event(event.event_id)
        assert retrieved is not None
        assert retrieved.event_id == event.event_id
        assert retrieved.event_type == EventType.HYPOTHESIS_GENERATED

    def test_list_events(self, store):
        e1 = BaseEvent(event_type=EventType.VALIDATION_STARTED, source_module="test")
        e2 = BaseEvent(event_type=EventType.VALIDATION_COMPLETED, source_module="test")
        store.save_event(e1)
        store.save_event(e2)
        events = store.list_events()
        assert len(events) == 2

    def test_list_events_by_type(self, store):
        e1 = BaseEvent(event_type=EventType.VALIDATION_PASSED, source_module="test")
        e2 = BaseEvent(event_type=EventType.VALIDATION_FAILED, source_module="test")
        e3 = BaseEvent(event_type=EventType.VALIDATION_PASSED, source_module="test")
        store.save_event(e1)
        store.save_event(e2)
        store.save_event(e3)
        passed = store.list_events_by_type(EventType.VALIDATION_PASSED)
        assert len(passed) == 2

    def test_list_events_by_correlation_id(self, store):
        e1 = BaseEvent(
            event_type=EventType.HYPOTHESIS_GENERATED,
            source_module="test",
            correlation_id="corr-001",
        )
        e2 = BaseEvent(
            event_type=EventType.HYPOTHESIS_FALSIFIED,
            source_module="test",
            correlation_id="corr-001",
        )
        e3 = BaseEvent(
            event_type=EventType.HYPOTHESIS_REJECTED,
            source_module="test",
            correlation_id="corr-002",
        )
        store.save_event(e1)
        store.save_event(e2)
        store.save_event(e3)
        corr_events = store.list_events_by_correlation_id("corr-001")
        assert len(corr_events) == 2

    def test_clear_events(self, store):
        event = BaseEvent(event_type=EventType.RISK_BLOCKED, source_module="test")
        store.save_event(event)
        store.clear_events()
        assert store.count == 0

    def test_get_nonexistent_event(self, store):
        retrieved = store.get_event("nonexistent")
        assert retrieved is None

    def test_count(self, store):
        assert store.count == 0
        for _ in range(5):
            event = BaseEvent(
                event_type=EventType.MARKET_OBSERVATION_CREATED,
                source_module="test",
            )
            store.save_event(event)
        assert store.count == 5
