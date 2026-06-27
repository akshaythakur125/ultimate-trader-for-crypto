from typing import Optional

from ultimate_trader.liquidity_smart_money.models import (
    Candle,
    StructureEvent,
    StructureType,
    SwingPoint,
    SwingType,
)


class MarketStructureEngine:
    def __init__(self, lookback: int = 5):
        self.lookback = lookback
        self._events: list[StructureEvent] = []

    def analyze(
        self,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        candles: list[Candle],
    ) -> list[StructureEvent]:
        new_events: list[StructureEvent] = []

        if len(swing_highs) < 2 or len(swing_lows) < 2 or len(candles) < self.lookback:
            return new_events

        bos = self._detect_bos(swing_highs, swing_lows, candles)
        new_events.extend(bos)

        choch = self._detect_choch(swing_highs, swing_lows, candles)
        new_events.extend(choch)

        mss = self._detect_mss(swing_highs, swing_lows, candles)
        new_events.extend(mss)

        continuation = self._detect_trend_continuation(swing_highs, swing_lows, candles)
        new_events.extend(continuation)

        failure = self._detect_structure_failure(swing_highs, swing_lows, candles)
        new_events.extend(failure)

        range_evt = self._detect_range(candles)
        new_events.extend(range_evt)

        compression = self._detect_compression(candles)
        new_events.extend(compression)

        self._events.extend(new_events)
        if len(self._events) > 50:
            self._events = self._events[-50:]

        return new_events

    def _detect_bos(
        self, swing_highs: list[SwingPoint], swing_lows: list[SwingPoint], candles: list[Candle]
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if len(candles) < 2:
            return events
        current = candles[-1]

        if swing_highs and current.high > swing_highs[-1].price and len(swing_highs) >= 2:
            events.append(StructureEvent(
                structure_type=StructureType.BOS,
                direction="BULLISH",
                price=current.high,
                index=len(candles) - 1,
                description=f"Bullish BOS: price broke above prior swing high {swing_highs[-1].price:.2f}",
            ))

        if swing_lows and current.low < swing_lows[-1].price and len(swing_lows) >= 2:
            events.append(StructureEvent(
                structure_type=StructureType.BOS,
                direction="BEARISH",
                price=current.low,
                index=len(candles) - 1,
                description=f"Bearish BOS: price broke below prior swing low {swing_lows[-1].price:.2f}",
            ))

        return events

    def _detect_choch(
        self, swing_highs: list[SwingPoint], swing_lows: list[SwingPoint], candles: list[Candle]
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if len(swing_highs) < 3 or len(swing_lows) < 3 or len(candles) < 3:
            return events

        recent_highs = swing_highs[-3:]
        recent_lows = swing_lows[-3:]
        current = candles[-1]

        if (recent_highs[-1].price < recent_highs[-2].price
                and current.high > recent_highs[-1].price
                and current.close > recent_highs[-1].price):
            events.append(StructureEvent(
                structure_type=StructureType.CHOCH,
                direction="BULLISH",
                price=current.high,
                index=len(candles) - 1,
                description="Bullish CHoCH: prior high broken after lower highs",
            ))

        if (recent_lows[-1].price > recent_lows[-2].price
                and current.low < recent_lows[-1].price
                and current.close < recent_lows[-1].price):
            events.append(StructureEvent(
                structure_type=StructureType.CHOCH,
                direction="BEARISH",
                price=current.low,
                index=len(candles) - 1,
                description="Bearish CHoCH: prior low broken after higher lows",
            ))

        return events

    def _detect_mss(
        self, swing_highs: list[SwingPoint], swing_lows: list[SwingPoint], candles: list[Candle]
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if len(swing_highs) < 2 or len(swing_lows) < 2 or len(candles) < 3:
            return events
        current = candles[-1]
        prev = candles[-2]

        if (swing_highs and current.high > swing_highs[-1].price
                and prev.low < swing_lows[-1].price if swing_lows else False):
            events.append(StructureEvent(
                structure_type=StructureType.MSS,
                direction="BULLISH",
                price=current.close,
                index=len(candles) - 1,
                description="Bullish MSS: structure shift with prior low sweep",
            ))

        if (swing_lows and current.low < swing_lows[-1].price
                and prev.high > swing_highs[-1].price if swing_highs else False):
            events.append(StructureEvent(
                structure_type=StructureType.MSS,
                direction="BEARISH",
                price=current.close,
                index=len(candles) - 1,
                description="Bearish MSS: structure shift with prior high sweep",
            ))

        return events

    def _detect_trend_continuation(
        self, swing_highs: list[SwingPoint], swing_lows: list[SwingPoint], candles: list[Candle]
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if len(candles) < 3 or len(swing_highs) < 2 or len(swing_lows) < 2:
            return events
        if (swing_highs[-1].price > swing_highs[-2].price
                and swing_lows[-1].price > swing_lows[-2].price):
            events.append(StructureEvent(
                structure_type=StructureType.TREND_CONTINUATION,
                direction="BULLISH",
                price=candles[-1].close,
                index=len(candles) - 1,
                description="Bullish trend continuation: higher highs and higher lows",
            ))
        if (swing_lows[-1].price < swing_lows[-2].price
                and swing_highs[-1].price < swing_highs[-2].price):
            events.append(StructureEvent(
                structure_type=StructureType.TREND_CONTINUATION,
                direction="BEARISH",
                price=candles[-1].close,
                index=len(candles) - 1,
                description="Bearish trend continuation: lower lows and lower highs",
            ))
        return events

    def _detect_structure_failure(
        self, swing_highs: list[SwingPoint], swing_lows: list[SwingPoint], candles: list[Candle]
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if len(candles) < 3 or len(swing_highs) < 2 or len(swing_lows) < 2:
            return events
        if (swing_highs[-1].price < swing_highs[-2].price
                and swing_lows[-1].price > swing_lows[-2].price):
            events.append(StructureEvent(
                structure_type=StructureType.STRUCTURE_FAILURE,
                direction="NEUTRAL",
                price=candles[-1].close,
                index=len(candles) - 1,
                description="Structure failure: contracting range",
            ))
        return events

    def _detect_range(self, candles: list[Candle]) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if len(candles) < 10:
            return events
        recent = candles[-10:]
        range_high = max(c.high for c in recent)
        range_low = min(c.low for c in recent)
        range_pct = ((range_high - range_low) / range_low) * 100 if range_low > 0 else 0
        if range_pct < 2.0:
            events.append(StructureEvent(
                structure_type=StructureType.RANGE,
                direction="NEUTRAL",
                price=candles[-1].close,
                index=len(candles) - 1,
                description=f"Range structure: {range_pct:.2f}% range over 10 candles",
            ))
        return events

    def _detect_compression(self, candles: list[Candle]) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        if len(candles) < 6:
            return events
        recent = candles[-6:]
        ranges = [c.high - c.low for c in recent]
        avg_range = sum(ranges) / len(ranges)
        latest = ranges[-1]
        if latest < avg_range * 0.5 and avg_range > 0:
            events.append(StructureEvent(
                structure_type=StructureType.COMPRESSION,
                direction="NEUTRAL",
                price=candles[-1].close,
                index=len(candles) - 1,
                description="Compression before expansion",
            ))
        return events

    def get_events(self) -> list[StructureEvent]:
        return list(self._events)

    def get_recent_events(self, n: int = 10) -> list[StructureEvent]:
        return self._events[-n:]

    def reset(self):
        self._events.clear()
