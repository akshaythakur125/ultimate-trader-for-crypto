import pytest

from ultimate_trader.event_bus import EventBus, EventType
from ultimate_trader.event_bus.events import BaseEvent


class TestEventBus:
    def test_publish_and_subscribe(self):
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        event = BaseEvent(
            event_type=EventType.HYPOTHESIS_GENERATED,
            source_module="test",
        )
        bus.subscribe(EventType.HYPOTHESIS_GENERATED, handler)
        bus.publish(event)

        assert len(received) == 1
        assert received[0].event_id == event.event_id

    def test_failed_handler_does_not_crash_bus(self):
        bus = EventBus()
        results = []

        def failing_handler(event):
            raise ValueError("Handler failed")

        def good_handler(event):
            results.append("ok")

        event = BaseEvent(
            event_type=EventType.VALIDATION_STARTED,
            source_module="test",
        )
        bus.subscribe(EventType.VALIDATION_STARTED, failing_handler)
        bus.subscribe(EventType.VALIDATION_STARTED, good_handler)
        bus.publish(event)

        assert results == ["ok"]

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        event = BaseEvent(
            event_type=EventType.SIGNAL_REJECTED,
            source_module="test",
        )
        bus.subscribe(EventType.SIGNAL_REJECTED, handler)
        bus.unsubscribe(EventType.SIGNAL_REJECTED, handler)
        bus.publish(event)

        assert len(received) == 0

    def test_wildcard_subscriber_receives_all(self):
        bus = EventBus()
        received = []

        def wildcard(event):
            received.append(event.event_type)

        bus.subscribe_all(wildcard)
        bus.publish(BaseEvent(
            event_type=EventType.MARKET_OBSERVATION_CREATED,
            source_module="test",
        ))
        bus.publish(BaseEvent(
            event_type=EventType.BELIEF_UPDATED,
            source_module="test",
        ))

        assert len(received) == 2

    def test_publish_batch(self):
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(EventType.BELIEF_UPDATED, handler)
        events = [
            BaseEvent(event_type=EventType.BELIEF_UPDATED, source_module="test"),
            BaseEvent(event_type=EventType.BELIEF_UPDATED, source_module="test"),
        ]
        bus.publish_batch(events)

        assert len(received) == 2

    def test_list_subscribers(self):
        bus = EventBus()

        def handler1(event):
            pass

        def handler2(event):
            pass

        bus.subscribe(EventType.RISK_BLOCKED, handler1)
        bus.subscribe(EventType.RISK_BLOCKED, handler2)

        subs = bus.list_subscribers(EventType.RISK_BLOCKED)
        assert len(subs) == 2

    def test_clear_subscribers(self):
        bus = EventBus()

        def handler(event):
            pass

        bus.subscribe(EventType.PAPER_TRADE_CREATED, handler)
        bus.clear_subscribers()

        subs = bus.list_subscribers()
        assert len(subs) == 0

    def test_event_has_required_fields(self):
        event = BaseEvent(
            event_type=EventType.MEMORY_REPORT_CREATED,
            source_module="memory_engine",
        )
        assert event.event_id is not None
        assert event.timestamp is not None
        assert event.payload == {}

    def test_event_with_correlation_id(self):
        event = BaseEvent(
            event_type=EventType.COGNITIVE_REASONING_COMPLETED,
            source_module="cognitive",
            correlation_id="corr-123",
        )
        assert event.correlation_id == "corr-123"

    def test_event_with_payload(self):
        event = BaseEvent(
            event_type=EventType.RESEARCH_REPORT_CREATED,
            source_module="research_brain",
            payload={"report_id": "RPT-001"},
        )
        assert event.payload["report_id"] == "RPT-001"

    def test_different_event_types(self):
        for et in EventType:
            event = BaseEvent(event_type=et, source_module="test")
            assert event.event_type == et
