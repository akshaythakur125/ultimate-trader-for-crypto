from ultimate_trader.orderflow_intelligence.iceberg_detector import IcebergDetector
from ultimate_trader.orderflow_intelligence.models import (
    AggressorSide,
    FlowWindow,
    IcebergSuspicion,
    TradePrint,
)


def make_trade(side: AggressorSide, qty: float = 1.0, price: float = 100.0) -> TradePrint:
    return TradePrint(
        symbol="BTCUSDT",
        price=price,
        quantity=qty,
        trade_value=price * qty,
        aggressor_side=side,
    )


def make_window(trades: list, total_value: float = 0.0, buy_vol: float = 0.0, sell_vol: float = 0.0) -> FlowWindow:
    return FlowWindow(
        symbol="BTCUSDT",
        trades=trades,
        trade_count=len(trades),
        total_trade_value=total_value,
        total_buy_volume=buy_vol,
        total_sell_volume=sell_vol,
        buy_sell_delta=buy_vol - sell_vol,
    )


class TestIcebergDetector:
    def test_insufficient_trades(self):
        d = IcebergDetector(repeat_trade_threshold=3)
        trades = [make_trade(AggressorSide.BUYER) for _ in range(2)]
        w = make_window(trades, total_value=200.0)
        r = d.analyze(w)
        assert r.iceberg_suspected == IcebergSuspicion.NONE
        assert "Insufficient" in r.explanation

    def test_no_repeated_price_level(self):
        d = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.BUYER, price=float(p)) for p in [100.0, 105.0, 110.0, 115.0, 120.0, 125.0]]
        w = make_window(trades, total_value=600.0)
        r = d.analyze(w)
        assert r.iceberg_suspected == IcebergSuspicion.NONE

    def test_iceberg_detected_with_repeats(self):
        d = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.BUYER, qty=1.0, price=100.0) for _ in range(5)]
        w = FlowWindow(
            symbol="BTCUSDT",
            trades=trades,
            trade_count=5,
            total_trade_value=500.0,
            total_buy_volume=5.0,
            total_sell_volume=0.0,
            buy_sell_delta=5.0,
        )
        r = d.analyze(w)
        assert r.iceberg_suspected != IcebergSuspicion.NONE
        assert r.side == "buy"
        assert r.price_level > 0
        assert r.confidence_score > 0

    def test_iceberg_on_sell_side(self):
        d = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.SELLER, qty=1.0, price=100.0) for _ in range(5)]
        w = FlowWindow(
            symbol="BTCUSDT",
            trades=trades,
            trade_count=5,
            total_trade_value=500.0,
            total_buy_volume=0.0,
            total_sell_volume=5.0,
            buy_sell_delta=-5.0,
        )
        r = d.analyze(w)
        assert r.iceberg_suspected != IcebergSuspicion.NONE
        assert r.side == "sell"

    def test_low_suspicion_for_few_repeats(self):
        d = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.BUYER, qty=0.1, price=100.0) for _ in range(3)]
        w = FlowWindow(
            symbol="BTCUSDT",
            trades=trades,
            trade_count=3,
            total_trade_value=30.0,
            total_buy_volume=0.3,
            total_sell_volume=0.0,
            buy_sell_delta=0.3,
        )
        r = d.analyze(w)
        assert r.iceberg_suspected in (IcebergSuspicion.LOW, IcebergSuspicion.NONE)

    def test_high_suspicion_for_many_repeats(self):
        d = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.BUYER, qty=2.0, price=100.0) for _ in range(10)]
        w = FlowWindow(
            symbol="BTCUSDT",
            trades=trades,
            trade_count=10,
            total_trade_value=2000.0,
            total_buy_volume=20.0,
            total_sell_volume=0.0,
            buy_sell_delta=20.0,
        )
        r = d.analyze(w)
        assert r.iceberg_suspected in (IcebergSuspicion.HIGH, IcebergSuspicion.MODERATE)

    def test_explanation_contains_details(self):
        d = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.BUYER, qty=1.0, price=100.0) for _ in range(5)]
        w = FlowWindow(
            symbol="BTCUSDT",
            trades=trades,
            trade_count=5,
            total_trade_value=500.0,
            total_buy_volume=5.0,
            total_sell_volume=0.0,
            buy_sell_delta=5.0,
        )
        r = d.analyze(w)
        assert "trades at" in r.explanation
        assert "iceberg suspicion" in r.explanation
