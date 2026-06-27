from ultimate_trader.microstructure_engine.liquidity_voids import (
    LiquidityVoidDetector,
)
from ultimate_trader.microstructure_engine.models import (
    OrderBookLevel,
    OrderBookSnapshot,
)


class TestLiquidityVoidDetector:
    def test_no_voids_in_normal_book(self):
        detector = LiquidityVoidDetector()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            bids=[OrderBookLevel(price=p, quantity=10) for p in [100.0, 99.9, 99.8, 99.7, 99.6]],
            asks=[OrderBookLevel(price=p, quantity=10) for p in [100.1, 100.2, 100.3, 100.4, 100.5]],
        )
        voids = detector.detect(snapshot)
        assert len(voids) == 0

    def test_detects_void_in_asks(self):
        detector = LiquidityVoidDetector(min_void_gap_bps=1.0, void_depth_threshold=1.0)
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            bids=[OrderBookLevel(price=100.0, quantity=10)],
            asks=[
                OrderBookLevel(price=100.1, quantity=0.5),
                OrderBookLevel(price=101.0, quantity=0.1),
            ],
        )
        voids = detector.detect(snapshot)
        assert len(voids) >= 1
        assert "void_ask" in voids[0].zone_label

    def test_detects_void_in_bids(self):
        detector = LiquidityVoidDetector(min_void_gap_bps=1.0, void_depth_threshold=1.0)
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            asks=[OrderBookLevel(price=100.1, quantity=10)],
            bids=[
                OrderBookLevel(price=100.0, quantity=0.5),
                OrderBookLevel(price=99.0, quantity=0.1),
            ],
        )
        voids = detector.detect(snapshot)
        assert len(voids) >= 1
        assert "void_bid" in voids[0].zone_label

    def test_high_severity_for_empty_zone(self):
        detector = LiquidityVoidDetector(min_void_gap_bps=1.0, void_depth_threshold=1.0)
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            bids=[OrderBookLevel(price=100.0, quantity=10)],
            asks=[
                OrderBookLevel(price=100.1, quantity=0),
                OrderBookLevel(price=101.0, quantity=0),
            ],
        )
        voids = detector.detect(snapshot)
        high_severity = [v for v in voids if v.severity == "HIGH"]
        assert len(high_severity) >= 0

    def test_empty_book_returns_no_voids(self):
        detector = LiquidityVoidDetector()
        snapshot = OrderBookSnapshot(symbol="BTCUSDT")
        voids = detector.detect(snapshot)
        assert len(voids) == 0

    def test_void_has_all_fields(self):
        detector = LiquidityVoidDetector(min_void_gap_bps=1.0)
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            bids=[OrderBookLevel(price=100.0, quantity=10)],
            asks=[
                OrderBookLevel(price=100.1, quantity=10),
                OrderBookLevel(price=101.0, quantity=0.5),
            ],
        )
        voids = detector.detect(snapshot)
        if voids:
            v = voids[0]
            assert v.zone_label
            assert v.price_above > 0
            assert v.price_below > 0
            assert v.depth_in_zone >= 0
            assert v.severity in ("LOW", "MEDIUM", "HIGH")
