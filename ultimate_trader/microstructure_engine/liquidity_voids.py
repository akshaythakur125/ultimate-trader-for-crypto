from typing import Optional

from ultimate_trader.microstructure_engine.models import (
    LiquidityVoid,
    OrderBookLevel,
    OrderBookSnapshot,
)


class LiquidityVoidDetector:
    def __init__(
        self,
        void_depth_threshold: float = 10.0,
        max_void_distance_percent: float = 2.0,
        min_void_gap_bps: float = 30.0,
    ):
        self.void_depth_threshold = void_depth_threshold
        self.max_void_distance_percent = max_void_distance_percent
        self.min_void_gap_bps = min_void_gap_bps

    def detect(self, snapshot: OrderBookSnapshot) -> list[LiquidityVoid]:
        voids: list[LiquidityVoid] = []
        if not snapshot.bids or not snapshot.asks:
            return voids

        voids.extend(self._detect_voids_above(snapshot))
        voids.extend(self._detect_voids_below(snapshot))
        return voids

    def _detect_voids_above(self, snapshot: OrderBookSnapshot) -> list[LiquidityVoid]:
        voids = []
        asks = snapshot.asks
        best_ask = snapshot.best_ask
        if not asks or best_ask <= 0:
            return voids

        for i in range(len(asks) - 1):
            current = asks[i]
            next_level = asks[i + 1]
            gap_bps = ((next_level.price - current.price) / current.price) * 10000
            if gap_bps >= self.min_void_gap_bps:
                distance_from_mid = ((current.price - snapshot.mid_price) / snapshot.mid_price) * 100
                if abs(distance_from_mid) <= self.max_void_distance_percent:
                    depth_in_zone = self._sum_depth_between(snapshot.asks, current.price, next_level.price)
                    if depth_in_zone < self.void_depth_threshold:
                        voids.append(
                            LiquidityVoid(
                                zone_label=f"void_ask_{current.price:.2f}-{next_level.price:.2f}",
                                price_above=next_level.price,
                                price_below=current.price,
                                depth_in_zone=round(depth_in_zone, 4),
                                severity="HIGH" if depth_in_zone == 0 else "MEDIUM",
                            )
                        )
        return voids

    def _detect_voids_below(self, snapshot: OrderBookSnapshot) -> list[LiquidityVoid]:
        voids = []
        bids = snapshot.bids
        best_bid = snapshot.best_bid
        if not bids or best_bid <= 0:
            return voids

        sorted_bids = sorted(bids, key=lambda x: x.price, reverse=True)
        for i in range(len(sorted_bids) - 1):
            current = sorted_bids[i]
            next_level = sorted_bids[i + 1]
            gap_bps = ((current.price - next_level.price) / current.price) * 10000
            if gap_bps >= self.min_void_gap_bps:
                distance_from_mid = ((current.price - snapshot.mid_price) / snapshot.mid_price) * 100
                if abs(distance_from_mid) <= self.max_void_distance_percent:
                    depth_in_zone = self._sum_depth_between(snapshot.bids, next_level.price, current.price)
                    if depth_in_zone < self.void_depth_threshold:
                        voids.append(
                            LiquidityVoid(
                                zone_label=f"void_bid_{next_level.price:.2f}-{current.price:.2f}",
                                price_above=current.price,
                                price_below=next_level.price,
                                depth_in_zone=round(depth_in_zone, 4),
                                severity="HIGH" if depth_in_zone == 0 else "MEDIUM",
                            )
                        )
        return voids

    def _sum_depth_between(
        self, levels: list[OrderBookLevel], lower: float, upper: float
    ) -> float:
        return sum(
            l.quantity for l in levels if lower < l.price < upper
        )
