from collections import Counter
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import (
    AggressorSide,
    FlowWindow,
    IcebergSuspicion,
)


class IcebergDetectionResult(BaseModel):
    iceberg_suspected: IcebergSuspicion = IcebergSuspicion.NONE
    side: str = ""
    price_level: float = 0.0
    confidence_score: float = 0.0
    explanation: str = ""


class IcebergDetector:
    def __init__(
        self,
        repeat_trade_threshold: int = 3,
        price_proximity_percent: float = 0.02,
        volume_ratio_threshold: float = 0.2,
    ):
        self.repeat_trade_threshold = repeat_trade_threshold
        self.price_proximity_percent = price_proximity_percent
        self.volume_ratio_threshold = volume_ratio_threshold

    def analyze(self, window: FlowWindow) -> IcebergDetectionResult:
        if window.trade_count < self.repeat_trade_threshold:
            return IcebergDetectionResult(
                explanation="Insufficient trades for iceberg detection"
            )

        price_groups = self._group_by_price(window)
        best_candidate = None
        best_score = 0.0

        for price_level, trades in price_groups.items():
            if len(trades) < self.repeat_trade_threshold:
                continue
            total_qty = sum(t.quantity for t in trades)
            buy_trades = sum(1 for t in trades if t.aggressor_side == AggressorSide.BUYER)
            sell_trades = sum(1 for t in trades if t.aggressor_side == AggressorSide.SELLER)
            trade_count = len(trades)
            volume_ratio = total_qty / window.total_trade_value if window.total_trade_value > 0 else 0

            score = self._compute_iceberg_score(
                trade_count, volume_ratio, buy_trades, sell_trades, total_qty, window
            )

            if score > best_score:
                best_score = score
                dominant_side = "buy" if buy_trades >= sell_trades else "sell"
                best_candidate = (price_level, dominant_side, total_qty, trade_count, score)

        if best_candidate is None:
            return IcebergDetectionResult(
                iceberg_suspected=IcebergSuspicion.NONE,
                explanation="No repeated price level patterns detected",
            )

        price, side, qty, count, score = best_candidate
        suspicion = self._classify_suspicion(score)

        return IcebergDetectionResult(
            iceberg_suspected=suspicion,
            side=side,
            price_level=price,
            confidence_score=round(score, 2),
            explanation=(
                f"{count} trades at {price:.2f} totaling {qty:.2f} units "
                f"on {side} side — possible {suspicion.value} iceberg suspicion"
            ),
        )

    def _group_by_price(self, window: FlowWindow) -> dict[float, list]:
        groups: dict[float, list] = {}
        for trade in window.trades:
            rounded = round(trade.price, int(-__import__("math").log10(self.price_proximity_percent * trade.price)) if trade.price > 0 else 2)
            found = False
            for existing_price in groups:
                if abs(existing_price - rounded) / max(existing_price, 0.001) <= self.price_proximity_percent:
                    groups[existing_price].append(trade)
                    found = True
                    break
            if not found:
                groups[rounded] = [trade]
        return groups

    def _compute_iceberg_score(
        self,
        trade_count: int,
        volume_ratio: float,
        buy_trades: int,
        sell_trades: int,
        total_qty: float,
        window: FlowWindow,
    ) -> float:
        count_score = min(trade_count / 10, 1.0) * 40
        vol_score = min(volume_ratio / self.volume_ratio_threshold, 1.0) * 30
        direction_score = 20 if abs(buy_trades - sell_trades) <= max(1, trade_count * 0.2) else 10
        repeat_score = 10 if trade_count >= self.repeat_trade_threshold * 2 else 0
        return count_score + vol_score + direction_score + repeat_score

    def _classify_suspicion(self, score: float) -> IcebergSuspicion:
        if score >= 70:
            return IcebergSuspicion.HIGH
        if score >= 45:
            return IcebergSuspicion.MODERATE
        if score >= 25:
            return IcebergSuspicion.LOW
        return IcebergSuspicion.NONE
