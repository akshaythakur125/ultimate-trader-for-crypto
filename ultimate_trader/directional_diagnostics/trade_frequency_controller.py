from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any


class TradeFrequencyResult:
    def __init__(self):
        self.allowed: bool = True
        self.rejection_reason: str = ""
        self.daily_trade_count: int = 0
        self.remaining_daily_slots: int = 6
        self.adjusted_confidence_threshold: float = 60.0


class TradeFrequencyController:
    def __init__(
        self,
        target_trades_per_day: int = 4,
        hard_max_candidates_per_day: int = 6,
        same_direction_cooldown_minutes: int = 120,
        same_symbol_cooldown_minutes: int = 60,
        confidence_after_first_loss: float = 70.0,
        confidence_after_second_loss: float = 85.0,
        base_confidence_threshold: float = 60.0,
    ):
        self.target_trades_per_day = target_trades_per_day
        self.hard_max_candidates_per_day = hard_max_candidates_per_day
        self.same_direction_cooldown_minutes = same_direction_cooldown_minutes
        self.same_symbol_cooldown_minutes = same_symbol_cooldown_minutes
        self.confidence_after_first_loss = confidence_after_first_loss
        self.confidence_after_second_loss = confidence_after_second_loss
        self.base_confidence_threshold = base_confidence_threshold

        self._daily_counts: dict[str, int] = defaultdict(int)
        self._daily_losses: dict[str, int] = defaultdict(int)
        self._last_trade_by_symbol: dict[str, datetime] = {}
        self._last_trade_by_direction: dict[str, datetime] = {}

    def check(
        self,
        symbol: str,
        direction: str,
        timestamp: datetime,
        confidence: float = 60.0,
    ) -> TradeFrequencyResult:
        result = TradeFrequencyResult()
        day_key = timestamp.strftime("%Y-%m-%d")
        current_count = self._daily_counts[day_key]
        current_losses = self._daily_losses[day_key]
        remaining = self.hard_max_candidates_per_day - current_count

        result.daily_trade_count = current_count
        result.remaining_daily_slots = max(0, remaining)
        result.adjusted_confidence_threshold = self.base_confidence_threshold

        if current_count >= self.hard_max_candidates_per_day:
            result.allowed = False
            result.rejection_reason = f"Daily candidate quota reached ({current_count}/{self.hard_max_candidates_per_day})"
            return result

        if current_losses >= 2:
            result.adjusted_confidence_threshold = self.confidence_after_second_loss
        elif current_losses >= 1:
            result.adjusted_confidence_threshold = self.confidence_after_first_loss

        if confidence < result.adjusted_confidence_threshold:
            result.allowed = False
            result.rejection_reason = (
                f"Confidence {confidence:.1f} < adjusted threshold {result.adjusted_confidence_threshold:.1f} "
                f"(base={self.base_confidence_threshold:.0f}, losses_today={current_losses})"
            )
            return result

        if direction in self._last_trade_by_direction:
            elapsed = (timestamp - self._last_trade_by_direction[direction]).total_seconds() / 60
            if elapsed < self.same_direction_cooldown_minutes:
                result.allowed = False
                result.rejection_reason = (
                    f"Same-direction cooldown: {elapsed:.0f}m < {self.same_direction_cooldown_minutes}m"
                )
                return result

        if symbol in self._last_trade_by_symbol:
            elapsed = (timestamp - self._last_trade_by_symbol[symbol]).total_seconds() / 60
            if elapsed < self.same_symbol_cooldown_minutes:
                result.allowed = False
                result.rejection_reason = (
                    f"Same-symbol cooldown: {elapsed:.0f}m < {self.same_symbol_cooldown_minutes}m"
                )
                return result

        return result

    def record_trade(
        self,
        symbol: str,
        direction: str,
        timestamp: datetime,
        was_loss: bool = False,
    ):
        day_key = timestamp.strftime("%Y-%m-%d")
        self._daily_counts[day_key] += 1
        if was_loss:
            self._daily_losses[day_key] += 1
        self._last_trade_by_symbol[symbol] = timestamp
        self._last_trade_by_direction[direction] = timestamp

    def reset(self):
        self._daily_counts.clear()
        self._daily_losses.clear()
        self._last_trade_by_symbol.clear()
        self._last_trade_by_direction.clear()
