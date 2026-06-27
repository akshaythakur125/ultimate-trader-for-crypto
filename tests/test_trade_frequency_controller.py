import pytest
from datetime import datetime, timedelta
from ultimate_trader.directional_diagnostics.trade_frequency_controller import (
    TradeFrequencyController,
    TradeFrequencyResult,
)


class TestTradeFrequencyController:
    def test_initial_allowed(self):
        ctrl = TradeFrequencyController()
        result = ctrl.check("BTCUSDT", "LONG", datetime(2025, 1, 1))
        assert result.allowed
        assert result.rejection_reason == ""

    def test_rejects_when_max_reached(self):
        ctrl = TradeFrequencyController(hard_max_candidates_per_day=2)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now)
        ctrl.record_trade("BTCUSDT", "SHORT", now)
        result = ctrl.check("BTCUSDT", "LONG", now)
        assert not result.allowed
        assert "quota reached" in result.rejection_reason.lower()

    def test_same_direction_cooldown(self):
        ctrl = TradeFrequencyController(same_direction_cooldown_minutes=60)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now)
        result = ctrl.check("ETHUSDT", "LONG", now + timedelta(minutes=30))
        assert not result.allowed
        assert "cooldown" in result.rejection_reason.lower()

    def test_different_direction_allows_cooldown(self):
        ctrl = TradeFrequencyController(same_direction_cooldown_minutes=60)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now)
        result = ctrl.check("ETHUSDT", "SHORT", now + timedelta(minutes=30))
        assert result.allowed

    def test_same_symbol_cooldown(self):
        ctrl = TradeFrequencyController(same_symbol_cooldown_minutes=60)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now)
        result = ctrl.check("BTCUSDT", "SHORT", now + timedelta(minutes=30))
        assert not result.allowed
        assert "cooldown" in result.rejection_reason.lower()

    def test_cooldown_expires(self):
        ctrl = TradeFrequencyController(same_symbol_cooldown_minutes=60)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now)
        result = ctrl.check("BTCUSDT", "SHORT", now + timedelta(minutes=90))
        assert result.allowed

    def test_confidence_after_first_loss(self):
        ctrl = TradeFrequencyController(confidence_after_first_loss=80.0, base_confidence_threshold=60.0)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now, was_loss=True)
        result = ctrl.check("ETHUSDT", "SHORT", now, confidence=75.0)
        assert not result.allowed
        assert "confidence" in result.rejection_reason.lower()

    def test_confidence_after_second_loss(self):
        ctrl = TradeFrequencyController(confidence_after_second_loss=90.0, base_confidence_threshold=60.0)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now, was_loss=True)
        ctrl.record_trade("ETHUSDT", "SHORT", now, was_loss=True)
        result = ctrl.check("ETHUSDT", "LONG", now, confidence=85.0)
        assert not result.allowed
        assert "confidence" in result.rejection_reason.lower()

    def test_reset_clears_state(self):
        ctrl = TradeFrequencyController()
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now)
        ctrl.reset()
        result = ctrl.check("BTCUSDT", "LONG", now)
        assert result.allowed

    def test_daily_count_tracking(self):
        ctrl = TradeFrequencyController(hard_max_candidates_per_day=6)
        now = datetime(2025, 1, 1)
        for i in range(3):
            ctrl.record_trade("BTCUSDT", "LONG", now + timedelta(hours=i))
        result = ctrl.check("ETHUSDT", "SHORT", now)
        assert result.daily_trade_count == 3
        assert result.remaining_daily_slots == 3
