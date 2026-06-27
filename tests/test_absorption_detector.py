from ultimate_trader.microstructure_engine.absorption_detector import (
    AbsorptionDetector,
)
from ultimate_trader.microstructure_engine.models import (
    OrderBookLevel,
    OrderBookSnapshot,
)


def make_absorbed_book(
    bid_aggressive: bool = False,
    ask_aggressive: bool = False,
    mid_price: float = 100.0,
) -> OrderBookSnapshot:
    bid_qty = [50.0, 30.0, 20.0] if not bid_aggressive else [2.0, 1.0, 1.0]
    ask_qty = [50.0, 30.0, 20.0] if not ask_aggressive else [2.0, 1.0, 1.0]
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=mid_price - 0.1 * (i + 1), quantity=q) for i, q in enumerate(bid_qty)],
        asks=[OrderBookLevel(price=mid_price + 0.1 * (i + 1), quantity=q) for i, q in enumerate(ask_qty)],
    )


class TestAbsorptionDetector:
    def test_no_absorption_normal_book(self):
        detector = AbsorptionDetector()
        for _ in range(5):
            detector.analyze(make_absorbed_book())
        result = detector.analyze(make_absorbed_book())
        assert result.detected is False

    def test_absorption_not_detected_with_few_snapshots(self):
        detector = AbsorptionDetector()
        result = detector.analyze(make_absorbed_book())
        assert result.detected is False

    def test_reset_clears_history(self):
        detector = AbsorptionDetector()
        for _ in range(5):
            detector.analyze(make_absorbed_book())
        detector.reset()
        assert len(detector._history) == 0

    def test_absorption_has_all_fields(self):
        detector = AbsorptionDetector()
        for _ in range(5):
            detector.analyze(make_absorbed_book())
        result = detector.analyze(make_absorbed_book())
        assert hasattr(result, "detected")
        assert hasattr(result, "absorption_type")
        assert hasattr(result, "strength")
        assert hasattr(result, "description")
