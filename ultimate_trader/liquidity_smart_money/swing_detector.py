from typing import Optional

from ultimate_trader.liquidity_smart_money.models import (
    Candle,
    SwingPoint,
    SwingType,
)


class SwingDetector:
    def __init__(self, lookback: int = 5, equal_threshold: float = 0.001):
        self.lookback = lookback
        self.equal_threshold = equal_threshold
        self._candles: list[Candle] = []
        self._swing_points: list[SwingPoint] = []

    def add_candle(self, candle: Candle) -> list[SwingPoint]:
        self._candles.append(candle)
        if len(self._candles) > 100:
            self._candles.pop(0)
        new_swings = self._detect_swings()
        return new_swings

    def _detect_swings(self) -> list[SwingPoint]:
        new_swings: list[SwingPoint] = []
        if len(self._candles) < self.lookback * 2 + 1:
            return new_swings

        idx = len(self._candles) - self.lookback - 1
        if idx < 0:
            return new_swings
        candle = self._candles[idx]

        prev = self._candles[idx - self.lookback:idx]
        next_c = self._candles[idx + 1:idx + self.lookback + 1]

        if len(prev) < self.lookback or len(next_c) < self.lookback:
            return new_swings

        high = candle.high
        low = candle.low

        if all(high > c.high for c in prev) and all(high > c.high for c in next_c):
            sp = SwingPoint(price=high, index=idx, swing_type=SwingType.SWING_HIGH)
            self._swing_points.append(sp)
            new_swings.append(sp)

        if all(low < c.low for c in prev) and all(low < c.low for c in next_c):
            sp = SwingPoint(price=low, index=idx, swing_type=SwingType.SWING_LOW)
            self._swing_points.append(sp)
            new_swings.append(sp)

        equal_highs = self._detect_equal_highs(idx)
        new_swings.extend(equal_highs)
        equal_lows = self._detect_equal_lows(idx)
        new_swings.extend(equal_lows)

        return new_swings

    def _detect_equal_highs(self, idx: int) -> list[SwingPoint]:
        result: list[SwingPoint] = []
        if idx < 1:
            return result
        current = self._candles[idx]
        for i in range(max(0, idx - 5), idx):
            prev = self._candles[i]
            diff = abs(current.high - prev.high) / max(prev.high, 0.001)
            if diff <= self.equal_threshold:
                sp = SwingPoint(price=(current.high + prev.high) / 2, index=idx, swing_type=SwingType.EQUAL_HIGH)
                self._swing_points.append(sp)
                result.append(sp)
                break
        return result

    def _detect_equal_lows(self, idx: int) -> list[SwingPoint]:
        result: list[SwingPoint] = []
        if idx < 1:
            return result
        current = self._candles[idx]
        for i in range(max(0, idx - 5), idx):
            prev = self._candles[i]
            diff = abs(current.low - prev.low) / max(prev.low, 0.001)
            if diff <= self.equal_threshold:
                sp = SwingPoint(price=(current.low + prev.low) / 2, index=idx, swing_type=SwingType.EQUAL_LOW)
                self._swing_points.append(sp)
                result.append(sp)
                break
        return result

    def get_swing_highs(self) -> list[SwingPoint]:
        return [s for s in self._swing_points if s.swing_type == SwingType.SWING_HIGH]

    def get_swing_lows(self) -> list[SwingPoint]:
        return [s for s in self._swing_points if s.swing_type == SwingType.SWING_LOW]

    def get_equal_highs(self) -> list[SwingPoint]:
        return [s for s in self._swing_points if s.swing_type == SwingType.EQUAL_HIGH]

    def get_equal_lows(self) -> list[SwingPoint]:
        return [s for s in self._swing_points if s.swing_type == SwingType.EQUAL_LOW]

    def get_all_swing_points(self) -> list[SwingPoint]:
        return list(self._swing_points)

    def reset(self):
        self._candles.clear()
        self._swing_points.clear()

    def recent_high(self, n: int = 5) -> float:
        highs = [c.high for c in self._candles[-n:]] if self._candles else [0.0]
        return max(highs)

    def recent_low(self, n: int = 5) -> float:
        lows = [c.low for c in self._candles[-n:]] if self._candles else [0.0]
        return min(lows)

    def highest_swing_high(self) -> float:
        highs = self.get_swing_highs()
        return max((s.price for s in highs), default=0.0)

    def lowest_swing_low(self) -> float:
        lows = self.get_swing_lows()
        return min((s.price for s in lows), default=0.0)
