from ultimate_trader.paper_trading.account import PaperAccount
from ultimate_trader.paper_trading.order import OrderSide, OrderType, PaperOrder
from ultimate_trader.paper_trading.portfolio import ClosedTrade, PaperPosition


class TestPaperAccountInit:
    def test_default_initialization(self):
        acc = PaperAccount()
        assert acc.starting_balance == 100_000.0
        assert acc.balance == 100_000.0
        assert acc.currency == "USDT"
        assert acc.max_leverage == 1
        assert acc.total_pnl == 0.0
        assert acc.equity == 100_000.0
        assert acc.free_balance == 100_000.0
        assert len(acc.orders) == 0
        assert len(acc.positions) == 0
        assert len(acc.closed_trades) == 0

    def test_custom_balance(self):
        acc = PaperAccount(starting_balance=50000.0, currency="BTC")
        assert acc.balance == 50000.0
        assert acc.currency == "BTC"

    def test_unrealized_pnl_with_position(self):
        acc = PaperAccount()
        pos = PaperPosition(
            position_id="POS-001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=100.0,
            quantity=1.0,
            current_price=110.0,
        )
        acc.register_position(pos)
        assert acc.unrealized_pnl == 10.0
        assert acc.equity == 100_010.0

    def test_unrealized_pnl_no_positions(self):
        acc = PaperAccount()
        assert acc.unrealized_pnl == 0.0


class TestPaperAccountPnL:
    def test_pnl_positive_trade(self):
        acc = PaperAccount(starting_balance=10000.0)
        trade = ClosedTrade(
            trade_id="T-001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=100.0,
            exit_price=110.0,
            quantity=1.0,
            gross_pnl=10.0,
            net_pnl=9.9,
            fee=0.1,
            holding_time_hours=4.0,
            entry_time=__import__("datetime").datetime.utcnow(),
            exit_reason="target_hit",
            rr=3.0,
        )
        acc.add_closed_trade(trade)
        assert acc.total_pnl == 9.9
        assert acc.balance == 10009.9
        assert acc.total_pnl_percent == 0.099

    def test_pnl_negative_trade(self):
        acc = PaperAccount(starting_balance=10000.0)
        trade = ClosedTrade(
            trade_id="T-002",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=100.0,
            exit_price=90.0,
            quantity=1.0,
            gross_pnl=-10.0,
            net_pnl=-10.1,
            fee=0.1,
            holding_time_hours=2.0,
            entry_time=__import__("datetime").datetime.utcnow(),
            exit_reason="stop_hit",
            rr=1.0,
        )
        acc.add_closed_trade(trade)
        assert acc.total_pnl == -10.1
        assert acc.balance == 9989.9

    def test_multiple_trades(self):
        acc = PaperAccount(starting_balance=10000.0)
        acc.add_closed_trade(
            ClosedTrade(
                trade_id="T-001", symbol="BTCUSDT", side=OrderSide.BUY,
                entry_price=100.0, exit_price=110.0, quantity=1.0,
                gross_pnl=10.0, net_pnl=9.9, fee=0.1,
                holding_time_hours=1.0,
                entry_time=__import__("datetime").datetime.utcnow(),
            )
        )
        acc.add_closed_trade(
            ClosedTrade(
                trade_id="T-002", symbol="ETHUSDT", side=OrderSide.SELL,
                entry_price=2000.0, exit_price=1900.0, quantity=0.5,
                gross_pnl=50.0, net_pnl=49.9, fee=0.1,
                holding_time_hours=2.0,
                entry_time=__import__("datetime").datetime.utcnow(),
            )
        )
        assert acc.total_pnl == 59.8
        assert acc.balance == 10059.8


class TestPaperAccountPositionManagement:
    def test_register_and_get_position(self):
        acc = PaperAccount()
        pos = PaperPosition(
            position_id="POS-001", symbol="BTCUSDT",
            side=OrderSide.BUY, entry_price=100.0, quantity=1.0,
        )
        acc.register_position(pos)
        assert acc.get_position("POS-001") == pos
        assert acc.get_position("NONEXISTENT") is None

    def test_remove_position(self):
        acc = PaperAccount()
        pos = PaperPosition(
            position_id="POS-001", symbol="BTCUSDT",
            side=OrderSide.BUY, entry_price=100.0, quantity=1.0,
        )
        acc.register_position(pos)
        assert acc.remove_position("POS-001") is True
        assert acc.remove_position("NONEXISTENT") is False
        assert len(acc.positions) == 0

    def test_open_positions_filter(self):
        acc = PaperAccount()
        pos_open = PaperPosition(
            position_id="POS-001", symbol="BTCUSDT",
            side=OrderSide.BUY, entry_price=100.0, quantity=1.0,
            current_price=0.0,
        )
        pos_closed = PaperPosition(
            position_id="POS-002", symbol="ETHUSDT",
            side=OrderSide.SELL, entry_price=2000.0, quantity=0.5,
            current_price=0.0,
        )
        acc.register_position(pos_open)
        acc.register_position(pos_closed)
        assert len(acc.open_positions) == 2


class TestPaperAccountOrderManagement:
    def test_add_order(self):
        acc = PaperAccount()
        order = PaperOrder(
            order_id="ORD-001", symbol="BTCUSDT",
            side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01,
        )
        acc.add_order(order)
        assert len(acc.orders) == 1
        assert acc.orders[0].order_id == "ORD-001"


class TestPaperAccountUpdatePrice:
    def test_update_position_price(self):
        acc = PaperAccount()
        pos = PaperPosition(
            position_id="POS-001", symbol="BTCUSDT",
            side=OrderSide.BUY, entry_price=100.0, quantity=1.0,
        )
        acc.register_position(pos)
        acc.update_position_price("POS-001", 105.0)
        assert acc.get_position("POS-001").current_price == 105.0
        assert acc.unrealized_pnl == 5.0


class TestPaperAccountReset:
    def test_reset_clears_everything(self):
        acc = PaperAccount(starting_balance=10000.0)
        pos = PaperPosition(
            position_id="POS-001", symbol="BTCUSDT",
            side=OrderSide.BUY, entry_price=100.0, quantity=1.0,
        )
        acc.register_position(pos)
        acc.add_order(PaperOrder(order_id="ORD-001", symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01))
        acc.add_closed_trade(
            ClosedTrade(
                trade_id="T-001", symbol="BTCUSDT", side=OrderSide.BUY,
                entry_price=100.0, exit_price=110.0, quantity=1.0,
                gross_pnl=10.0, net_pnl=9.9, fee=0.1,
                holding_time_hours=1.0,
                entry_time=__import__("datetime").datetime.utcnow(),
            )
        )
        acc.reset()
        assert acc.balance == 10000.0
        assert acc.total_pnl == 0.0
        assert len(acc.orders) == 0
        assert len(acc.positions) == 0
        assert len(acc.closed_trades) == 0


class TestPaperAccountSummary:
    def test_summary_keys(self):
        acc = PaperAccount(starting_balance=50000.0)
        summary = acc.summary()
        assert summary["starting_balance"] == 50000.0
        assert summary["current_balance"] == 50000.0
        assert summary["currency"] == "USDT"
        assert "equity" in summary
        assert "total_pnl" in summary
        assert "open_positions" in summary
        assert "closed_trades" in summary

    def test_has_funds_for(self):
        acc = PaperAccount(starting_balance=1000.0)
        assert acc.has_funds_for(500.0) is True
        assert acc.has_funds_for(1500.0) is False
