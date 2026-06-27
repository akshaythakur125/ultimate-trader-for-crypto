from typing import Optional

from ultimate_trader.microstructure_engine.models import (
    DepthState,
    OrderBookLevel,
    OrderBookSnapshot,
)


class OrderBookDepthAnalyzer:
    def __init__(
        self,
        thin_book_quantity_threshold: float = 50.0,
        wall_quantity_threshold: float = 500.0,
    ):
        self.thin_book_quantity_threshold = thin_book_quantity_threshold
        self.wall_quantity_threshold = wall_quantity_threshold

    def analyze(self, snapshot: OrderBookSnapshot) -> DepthState:
        bid_depth = snapshot.bid_depth
        ask_depth = snapshot.ask_depth

        if bid_depth < self.thin_book_quantity_threshold and ask_depth < self.thin_book_quantity_threshold:
            return DepthState.CRITICAL

        if bid_depth < self.thin_book_quantity_threshold or ask_depth < self.thin_book_quantity_threshold:
            return DepthState.THIN

        imbalance = snapshot.depth_imbalance
        if abs(imbalance) > 0.5:
            return DepthState.IMBALANCED

        return DepthState.NORMAL

    def get_depth_imbalance_ratio(self, snapshot: OrderBookSnapshot) -> float:
        total = snapshot.bid_depth + snapshot.ask_depth
        if total == 0:
            return 0.0
        return abs(snapshot.bid_depth - snapshot.ask_depth) / total

    def find_liquidity_walls(
        self, snapshot: OrderBookSnapshot, levels: int = 5
    ) -> dict[str, list[dict]]:
        bid_walls = self._find_walls(snapshot.bids, snapshot.best_bid, "bid")
        ask_walls = self._find_walls(snapshot.asks, snapshot.best_ask, "ask")
        return {"bid_walls": bid_walls[:levels], "ask_walls": ask_walls[:levels]}

    def _find_walls(
        self, levels: list[OrderBookLevel], best_price: float, side: str
    ) -> list[dict]:
        walls = []
        for level in levels:
            if level.quantity >= self.wall_quantity_threshold:
                distance = abs(level.price - best_price) / best_price * 100 if best_price > 0 else 0
                walls.append({
                    "side": side,
                    "price": level.price,
                    "quantity": level.quantity,
                    "distance_percent": round(distance, 4),
                })
        return walls
