from typing import Optional

from ultimate_trader.liquidity_smart_money.models import (
    Candle,
    Displacement,
    LiquidityZone,
    Sweep,
)
from ultimate_trader.liquidity_smart_money.displacement import DisplacementEngine


class SweepDetector:
    def __init__(self, reclaim_threshold: float = 0.001):
        self.reclaim_threshold = reclaim_threshold
        self._sweeps: list[Sweep] = []

    def analyze(
        self,
        candles: list[Candle],
        liquidity_zones: list[LiquidityZone],
        displacement_engine: Optional[DisplacementEngine] = None,
    ) -> list[Sweep]:
        new_sweeps: list[Sweep] = []
        if len(candles) < 2:
            return new_sweeps

        for zone in liquidity_zones:
            if zone.is_swept and not self._already_recorded(zone):
                sweep = self._build_sweep(zone, candles, displacement_engine)
                if sweep:
                    new_sweeps.append(sweep)
                    self._sweeps.append(sweep)

        current = candles[-1]
        for zone in self._zones_crossed_by_current(current, liquidity_zones):
            if not zone.is_swept:
                sweep = self._build_realtime_sweep(zone, current, displacement_engine)
                if sweep:
                    new_sweeps.append(sweep)
                    self._sweeps.append(sweep)

        return new_sweeps

    def _already_recorded(self, zone: LiquidityZone) -> bool:
        for s in self._sweeps:
            if abs(s.sweep_low - zone.price_min) < 0.01 or abs(s.sweep_high - zone.price_max) < 0.01:
                return True
        return False

    def _build_sweep(
        self, zone: LiquidityZone, candles: list[Candle], displacement_engine: Optional[DisplacementEngine]
    ) -> Optional[Sweep]:
        entry = zone.price_min if zone.zone_type == "BUY_SIDE" else zone.price_max
        sweep_low = min(c.low for c in candles[-3:]) if zone.zone_type == "BUY_SIDE" else zone.price_min
        sweep_high = max(c.high for c in candles[-3:]) if zone.zone_type == "SELL_SIDE" else zone.price_max

        has_reclaim = False
        reclaim_price = None
        if zone.zone_type == "BUY_SIDE" and candles[-1].close < entry:
            has_reclaim = True
            reclaim_price = candles[-1].close
        elif zone.zone_type == "SELL_SIDE" and candles[-1].close > entry:
            has_reclaim = True
            reclaim_price = candles[-1].close

        displacement = None
        has_displacement = False
        if displacement_engine and len(candles) >= 3:
            displacement = displacement_engine.analyze(candles[-3:])
            has_displacement = displacement.is_displaced if displacement else False

        sweep_type = "BUY_SIDE_SWEEP" if zone.zone_type == "BUY_SIDE" else "SELL_SIDE_SWEEP"
        idx = zone.sweep_index if zone.sweep_index is not None else len(candles) - 1

        sweep = Sweep(
            sweep_type=sweep_type,
            entry_price=entry,
            sweep_low=sweep_low,
            sweep_high=sweep_high,
            reclaim_price=reclaim_price,
            has_reclaim=has_reclaim,
            is_failed=False,
            has_displacement=has_displacement,
            index=idx,
            description=self._build_description(sweep_type, has_reclaim, has_displacement),
        )
        return sweep

    def _build_realtime_sweep(
        self, zone: LiquidityZone, current: Candle, displacement_engine: Optional[DisplacementEngine]
    ) -> Optional[Sweep]:
        if zone.zone_type == "BUY_SIDE" and current.high >= zone.price_max:
            return None
        if zone.zone_type == "SELL_SIDE" and current.low <= zone.price_min:
            return None
        entry = zone.price_min if zone.zone_type == "BUY_SIDE" else zone.price_max
        sweep_type = "BUY_SIDE_SWEEP" if zone.zone_type == "BUY_SIDE" else "SELL_SIDE_SWEEP"
        sweep = Sweep(
            sweep_type=sweep_type,
            entry_price=entry,
            sweep_low=entry * 0.995,
            sweep_high=entry * 1.005,
            has_reclaim=False,
            is_failed=True,
            has_displacement=False,
            index=0,
            description=f"Failed {sweep_type.lower().replace('_', ' ')}",
        )
        return sweep

    def _zones_crossed_by_current(self, current: Candle, zones: list[LiquidityZone]) -> list[LiquidityZone]:
        return [
            z for z in zones
            if not z.is_swept and (
                (z.zone_type == "BUY_SIDE" and current.high >= z.price_min and current.low <= z.price_max)
                or (z.zone_type == "SELL_SIDE" and current.low <= z.price_max and current.high >= z.price_min)
            )
        ]

    def _build_description(self, sweep_type: str, has_reclaim: bool, has_displacement: bool) -> str:
        parts = [sweep_type.lower().replace("_", " ")]
        if has_reclaim:
            parts.append("with reclaim")
        if has_displacement:
            parts.append("with displacement")
        return " | ".join(parts)

    def get_sweeps(self) -> list[Sweep]:
        return list(self._sweeps)

    def get_recent_sweeps(self, n: int = 5) -> list[Sweep]:
        return self._sweeps[-n:]

    def reset(self):
        self._sweeps.clear()
