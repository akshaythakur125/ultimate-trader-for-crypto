from ultimate_trader.microstructure_engine.models import (
    ExecutionRisk,
    OrderBookLevel,
    OrderBookSnapshot,
)
from ultimate_trader.microstructure_engine.price_impact import (
    PriceImpactEstimator,
)


def make_snapshot(
    bid_qty: float = 50, ask_qty: float = 50, levels: int = 5
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=100.0 - i * 0.1, quantity=bid_qty) for i in range(levels)],
        asks=[OrderBookLevel(price=100.1 + i * 0.1, quantity=ask_qty) for i in range(levels)],
    )


class TestPriceImpactEstimator:
    def test_small_order_low_risk(self):
        estimator = PriceImpactEstimator()
        snapshot = make_snapshot(bid_qty=100, ask_qty=100)
        result = estimator.estimate(snapshot, order_quantity=1.0)
        assert result.execution_risk in (ExecutionRisk.LOW, ExecutionRisk.MEDIUM)
        assert result.expected_slippage_bps >= 0

    def test_large_order_higher_risk(self):
        estimator = PriceImpactEstimator()
        snapshot = make_snapshot(bid_qty=10, ask_qty=10)
        result = estimator.estimate(snapshot, order_quantity=100.0)
        assert result.execution_risk in (ExecutionRisk.HIGH, ExecutionRisk.CRITICAL)

    def test_empty_book_critical_risk(self):
        estimator = PriceImpactEstimator()
        snapshot = OrderBookSnapshot(symbol="BTCUSDT")
        result = estimator.estimate(snapshot, order_quantity=1.0)
        assert result.execution_risk == ExecutionRisk.CRITICAL

    def test_position_size_too_large(self):
        estimator = PriceImpactEstimator()
        snapshot = make_snapshot(bid_qty=5, ask_qty=5)
        result = estimator.estimate(snapshot, order_quantity=100.0)
        assert result.position_too_large is True

    def test_reason_present(self):
        estimator = PriceImpactEstimator()
        snapshot = make_snapshot()
        result = estimator.estimate(snapshot, order_quantity=1.0)
        assert len(result.reason) > 0

    def test_max_safe_quantity_returned(self):
        estimator = PriceImpactEstimator()
        snapshot = make_snapshot(bid_qty=100, ask_qty=100)
        result = estimator.estimate(snapshot, order_quantity=1.0)
        assert result.max_safe_order_quantity > 0
