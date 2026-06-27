from typing import Optional

from ultimate_trader.liquidity_smart_money.models import (
    Candle,
    LiquidityZone,
    SwingPoint,
    SwingType,
)


class LiquidityPoolDetector:
    def __init__(self, pool_strength_threshold: float = 2.0):
        self.pool_strength_threshold = pool_strength_threshold
        self._zones: list[LiquidityZone] = []

    def analyze(
        self,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        equal_highs: list[SwingPoint],
        equal_lows: list[SwingPoint],
        current_price: float,
        candles: list[Candle],
    ) -> list[LiquidityZone]:
        self._zones.clear()

        buy_side = self._detect_buy_side_liquidity(equal_highs, swing_highs, current_price)
        self._zones.extend(buy_side)

        sell_side = self._detect_sell_side_liquidity(equal_lows, swing_lows, current_price)
        self._zones.extend(sell_side)

        stop_clusters = self._detect_stop_clusters(candles, swing_highs, swing_lows)
        self._zones.extend(stop_clusters)

        self._mark_swept_zones(current_price, candles)
        return list(self._zones)

    def _detect_buy_side_liquidity(
        self, equal_highs: list[SwingPoint], swing_highs: list[SwingPoint], price: float
    ) -> list[LiquidityZone]:
        zones: list[LiquidityZone] = []
        targets = []

        for eq in equal_highs:
            if eq.price > price:
                targets.append((eq.price, 2.0, eq.index, f"equal_high_{eq.price:.2f}"))

        recent_sh = [s for s in swing_highs if len(self._zones) > 0 or s.price > price]
        for sh in swing_highs[-3:]:
            if sh.price > price:
                targets.append((sh.price, 1.5, sh.index, f"swing_high_{sh.price:.2f}"))

        for price_val, strength, idx, label in targets:
            zone = LiquidityZone(
                zone_type="BUY_SIDE",
                price_min=price_val * 0.998,
                price_max=price_val * 1.002,
                strength=strength,
                created_at_index=idx,
                label=label,
            )
            zones.append(zone)
        return zones

    def _detect_sell_side_liquidity(
        self, equal_lows: list[SwingPoint], swing_lows: list[SwingPoint], price: float
    ) -> list[LiquidityZone]:
        zones: list[LiquidityZone] = []
        targets = []

        for eq in equal_lows:
            if eq.price < price:
                targets.append((eq.price, 2.0, eq.index, f"equal_low_{eq.price:.2f}"))

        for sl in swing_lows[-3:]:
            if sl.price < price:
                targets.append((sl.price, 1.5, sl.index, f"swing_low_{sl.price:.2f}"))

        for price_val, strength, idx, label in targets:
            zone = LiquidityZone(
                zone_type="SELL_SIDE",
                price_min=price_val * 0.998,
                price_max=price_val * 1.002,
                strength=strength,
                created_at_index=idx,
                label=label,
            )
            zones.append(zone)
        return zones

    def _detect_stop_clusters(
        self, candles: list[Candle], swing_highs: list[SwingPoint], swing_lows: list[SwingPoint]
    ) -> list[LiquidityZone]:
        zones: list[LiquidityZone] = []
        if len(candles) < 5:
            return zones
        closes = [c.close for c in candles[-20:]]
        if not closes:
            return zones
        avg_vol = sum(c.volume for c in candles[-20:]) / max(len(candles[-20:]), 1)
        recent = candles[-5:]
        high_vol_clusters = [c for c in recent if c.volume > avg_vol * 1.5]
        if high_vol_clusters:
            zone_low = min(c.low for c in high_vol_clusters)
            zone_high = max(c.high for c in high_vol_clusters)
            zones.append(LiquidityZone(
                zone_type="STOP_CLUSTER",
                price_min=zone_low,
                price_max=zone_high,
                strength=1.0,
                label=f"stop_cluster_{zone_low:.2f}_{zone_high:.2f}",
            ))
        return zones

    def _mark_swept_zones(self, current_price: float, candles: list[Candle]):
        for zone in self._zones:
            if zone.is_swept:
                continue
            if zone.zone_type == "BUY_SIDE" and current_price >= zone.price_max:
                zone.is_swept = True
            elif zone.zone_type == "SELL_SIDE" and current_price <= zone.price_min:
                zone.is_swept = True

        mid = len(candles) // 2 if candles else 0
        for zone in self._zones:
            for i, c in enumerate(candles):
                if zone.zone_type == "BUY_SIDE" and c.high >= zone.price_max:
                    zone.is_swept = True
                    zone.sweep_index = i
                    break
                if zone.zone_type == "SELL_SIDE" and c.low <= zone.price_min:
                    zone.is_swept = True
                    zone.sweep_index = i
                    break

    def get_active_zones(self) -> list[LiquidityZone]:
        return [z for z in self._zones if not z.is_swept]

    def get_swept_zones(self) -> list[LiquidityZone]:
        return [z for z in self._zones if z.is_swept]

    def reset(self):
        self._zones.clear()
