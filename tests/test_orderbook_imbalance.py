from ultimate_trader.microstructure_engine.models import (
    OrderBookLevel,
    OrderBookSnapshot,
)
from ultimate_trader.microstructure_engine.orderbook_imbalance import (
    ImbalanceBias,
    OrderBookImbalanceAnalyzer,
)


def make_snapshot(bid_qty: float, ask_qty: float) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=p, quantity=q) for p, q in
              [(100.0, bid_qty), (99.9, bid_qty * 0.5), (99.8, bid_qty * 0.3)]],
        asks=[OrderBookLevel(price=p, quantity=q) for p, q in
              [(100.1, ask_qty), (100.2, ask_qty * 0.5), (100.3, ask_qty * 0.3)]],
    )


class TestOrderBookImbalanceAnalyzer:
    def test_bid_dominance_produces_long_bias(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snapshot = make_snapshot(bid_qty=100.0, ask_qty=10.0)
        result = analyzer.analyze(snapshot)
        assert result.bias == ImbalanceBias.LONG
        assert result.imbalance_score > 50

    def test_ask_dominance_produces_short_bias(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snapshot = make_snapshot(bid_qty=10.0, ask_qty=100.0)
        result = analyzer.analyze(snapshot)
        assert result.bias == ImbalanceBias.SHORT
        assert result.imbalance_score < 50

    def test_balanced_book_produces_neutral(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snapshot = make_snapshot(bid_qty=50.0, ask_qty=50.0)
        result = analyzer.analyze(snapshot)
        assert result.bias == ImbalanceBias.NEUTRAL
        assert 40 <= result.imbalance_score <= 60

    def test_empty_book_returns_neutral(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snapshot = OrderBookSnapshot(symbol="BTCUSDT")
        result = analyzer.analyze(snapshot)
        assert result.bias == ImbalanceBias.NEUTRAL
        assert result.imbalance_score == 50.0

    def test_imbalance_reason_present(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snapshot = make_snapshot(bid_qty=80.0, ask_qty=20.0)
        result = analyzer.analyze(snapshot)
        assert len(result.imbalance_reason) > 0
        assert "bid" in result.imbalance_reason.lower()

    def test_imbalance_score_range(self):
        analyzer = OrderBookImbalanceAnalyzer()
        for bid, ask in [(100, 0), (0, 100), (50, 50), (75, 25), (25, 75)]:
            snapshot = make_snapshot(bid_qty=float(bid), ask_qty=float(ask))
            result = analyzer.analyze(snapshot)
            assert 0 <= result.imbalance_score <= 100

    def test_strong_bid_dominance(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snapshot = make_snapshot(bid_qty=200.0, ask_qty=5.0)
        result = analyzer.analyze(snapshot)
        assert result.bias == ImbalanceBias.LONG
        assert "strong" in result.imbalance_reason.lower()

    def test_strong_ask_dominance(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snapshot = make_snapshot(bid_qty=5.0, ask_qty=200.0)
        result = analyzer.analyze(snapshot)
        assert result.bias == ImbalanceBias.SHORT
        assert "strong" in result.imbalance_reason.lower()


class TestOrderBookImbalanceAnalyzerCustomDepth:
    def test_respects_depth_levels(self):
        analyzer = OrderBookImbalanceAnalyzer(depth_levels=2)
        snapshot = make_snapshot(bid_qty=100.0, ask_qty=10.0)
        result = analyzer.analyze(snapshot)
        assert result.bias == ImbalanceBias.LONG
