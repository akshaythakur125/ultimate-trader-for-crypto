from typing import Optional

from ultimate_trader.liquidity_smart_money.models import Candle, Displacement


class DisplacementEngine:
    def __init__(self, range_threshold: float = 1.5, volume_threshold: float = 1.3):
        self.range_threshold = range_threshold
        self.volume_threshold = volume_threshold
        self._displacements: list[Displacement] = []

    def analyze(self, candles: list[Candle]) -> Optional[Displacement]:
        if len(candles) < 3:
            return None

        current = candles[-1]
        prev_candles = candles[:-1]
        avg_range = sum(c.high - c.low for c in prev_candles) / max(len(prev_candles), 1)
        avg_vol = sum(c.volume for c in prev_candles) / max(len(prev_candles), 1)

        current_range = current.high - current.low
        range_ratio = current_range / max(avg_range, 0.001)
        vol_ratio = current.volume / max(avg_vol, 0.001)

        direction = "UP" if current.close > current.open else ("DOWN" if current.close < current.open else "NEUTRAL")
        if direction == "NEUTRAL":
            return None

        is_strong = range_ratio >= self.range_threshold and vol_ratio >= self.volume_threshold
        is_weak = range_ratio < 0.7
        is_volume_supported = vol_ratio >= self.volume_threshold and range_ratio >= 1.0
        is_fake = range_ratio >= self.range_threshold and vol_ratio < 0.7

        dtype = "STRONG" if is_strong else "WEAK" if is_weak else "VOLUME_SUPPORTED" if is_volume_supported else "FAKE" if is_fake else "NORMAL"

        d = Displacement(
            is_displaced=is_strong or is_volume_supported,
            displacement_type=dtype,
            candle_range=round(current_range, 2),
            volume_ratio=round(vol_ratio, 2),
            direction=direction,
            index=len(candles) - 1,
            description=self._build_description(dtype, direction, range_ratio, vol_ratio),
        )
        self._displacements.append(d)
        if len(self._displacements) > 50:
            self._displacements.pop(0)
        return d

    def analyze_after_sweep(self, candles: list[Candle], sweep_index: int) -> Optional[Displacement]:
        if len(candles) < 3 or sweep_index >= len(candles) - 1:
            return None
        post_sweep = candles[sweep_index + 1:]
        if len(post_sweep) < 2:
            return None
        result = self.analyze(post_sweep)
        if result and result.is_displaced:
            result.displacement_type = "AFTER_SWEEP"
            result.description = f"Displacement after sweep: {result.direction} ({result.candle_range:.2f} range, vol_ratio={result.volume_ratio:.2f})"
        return result

    def _build_description(self, dtype: str, direction: str, range_ratio: float, vol_ratio: float) -> str:
        return f"{dtype} {direction} displacement (range_ratio={range_ratio:.2f}, vol_ratio={vol_ratio:.2f})"

    def get_displacements(self) -> list[Displacement]:
        return list(self._displacements)

    def reset(self):
        self._displacements.clear()
