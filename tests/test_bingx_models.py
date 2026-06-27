from datetime import datetime, timezone

from ultimate_trader.bingx.models import (
    ExchangeSymbol,
    Kline,
    OrderBook,
    OrderBookLevel,
    Ticker,
)


class TestKline:
    def test_create_kline(self):
        k = Kline(
            symbol="BTCUSDT",
            interval="1h",
            open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open_price=100.0,
            high_price=110.0,
            low_price=99.0,
            close_price=105.0,
            volume=1000.0,
            close_time=datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
            quote_volume=105000.0,
            trade_count=250,
        )
        assert k.symbol == "BTCUSDT"
        assert k.close_price == 105.0


class TestTicker:
    def test_create_ticker(self):
        t = Ticker(
            symbol="BTCUSDT",
            last_price=50000.0,
            price_change_percent=1.5,
            high_price=51000.0,
            low_price=49000.0,
            volume=1000.0,
            quote_volume=50000000.0,
        )
        assert t.symbol == "BTCUSDT"
        assert t.last_price == 50000.0


class TestOrderBookLevel:
    def test_create_level(self):
        lvl = OrderBookLevel(price=100.0, quantity=1.5)
        assert lvl.price == 100.0
        assert lvl.quantity == 1.5


class TestOrderBook:
    def test_create_order_book(self):
        ob = OrderBook(
            symbol="BTCUSDT",
            bids=[OrderBookLevel(price=100.0, quantity=1.5)],
            asks=[OrderBookLevel(price=101.0, quantity=2.0)],
            last_update_id=12345,
        )
        assert ob.symbol == "BTCUSDT"
        assert len(ob.bids) == 1
        assert len(ob.asks) == 1

    def test_empty_order_book(self):
        ob = OrderBook(symbol="BTCUSDT")
        assert len(ob.bids) == 0
        assert len(ob.asks) == 0


class TestExchangeSymbol:
    def test_create_symbol(self):
        s = ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            base_asset="BTC",
            quote_asset="USDT",
            min_qty=0.001,
            max_qty=100.0,
            step_size=0.001,
            tick_size=0.01,
        )
        assert s.symbol == "BTCUSDT"
        assert s.status == "TRADING"
        assert s.base_asset == "BTC"
        assert s.quote_asset == "USDT"
