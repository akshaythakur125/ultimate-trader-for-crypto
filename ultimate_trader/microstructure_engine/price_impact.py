from typing import Optional

from ultimate_trader.microstructure_engine.models import (
    ExecutionRisk,
    OrderBookSnapshot,
    PriceImpactEstimate,
)


class PriceImpactEstimator:
    def __init__(
        self,
        small_order_quantity: float = 1.0,
        medium_order_quantity: float = 5.0,
        large_order_quantity: float = 20.0,
        max_slippage_bps: float = 10.0,
    ):
        self.small_order_quantity = small_order_quantity
        self.medium_order_quantity = medium_order_quantity
        self.large_order_quantity = large_order_quantity
        self.max_slippage_bps = max_slippage_bps

    def estimate(
        self, snapshot: OrderBookSnapshot, order_quantity: float
    ) -> PriceImpactEstimate:
        if not snapshot.asks or not snapshot.bids:
            return PriceImpactEstimate(
                execution_risk=ExecutionRisk.CRITICAL,
                reason="No order book data available",
            )

        buy_slippage = self._estimate_slippage(snapshot.asks, snapshot.best_ask, order_quantity, "buy")
        sell_slippage = self._estimate_slippage(snapshot.bids, snapshot.best_bid, order_quantity, "sell")
        avg_slippage = (buy_slippage + sell_slippage) / 2.0

        max_safe = self._compute_max_safe_quantity(snapshot)
        too_large = order_quantity > max_safe

        risk = self._classify_risk(avg_slippage, too_large)
        reason = self._build_reason(avg_slippage, too_large, order_quantity, max_safe)

        return PriceImpactEstimate(
            expected_slippage_bps=round(avg_slippage, 2),
            position_too_large=too_large,
            execution_risk=risk,
            max_safe_order_quantity=round(max_safe, 4),
            reason=reason,
        )

    def _estimate_slippage(
        self,
        levels: list,
        best_price: float,
        order_qty: float,
        side: str,
    ) -> float:
        if best_price <= 0:
            return 999.0
        remaining = order_qty
        total_cost = 0.0
        filled = 0.0
        for level in levels:
            if remaining <= 0:
                break
            take = min(remaining, level.quantity)
            total_cost += take * level.price
            filled += take
            remaining -= take
        if filled == 0:
            return 999.0
        avg_price = total_cost / filled
        slippage_bps = abs(avg_price - best_price) / best_price * 10000
        return slippage_bps

    def _compute_max_safe_quantity(self, snapshot: OrderBookSnapshot) -> float:
        if not snapshot.asks or not snapshot.bids:
            return 0.0
        total_depth = snapshot.bid_depth + snapshot.ask_depth
        return total_depth * 0.1

    def _classify_risk(self, slippage_bps: float, too_large: bool) -> ExecutionRisk:
        if too_large or slippage_bps > self.max_slippage_bps * 3:
            return ExecutionRisk.CRITICAL
        if slippage_bps > self.max_slippage_bps * 2:
            return ExecutionRisk.HIGH
        if slippage_bps > self.max_slippage_bps:
            return ExecutionRisk.MEDIUM
        if too_large:
            return ExecutionRisk.HIGH
        return ExecutionRisk.LOW

    def _build_reason(
        self, slippage: float, too_large: bool, qty: float, max_safe: float
    ) -> str:
        parts = [f"estimated slippage {slippage:.1f} bps"]
        if too_large:
            parts.append(f"order {qty:.2f} exceeds safe limit {max_safe:.4f}")
        return " | ".join(parts)
