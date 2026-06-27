import pytest
from datetime import datetime, timedelta
from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection, ExitReason
from ultimate_trader.drawdown_control.rolling_performance_monitor import RollingPerformanceMonitor


def make_trade(trade_id: str, net_r: float, signal_time: datetime, symbol: str = "BTCUSDT"):
    return ReplayTrade(
        trade_id=trade_id, symbol=symbol, direction=TradeDirection.LONG,
        signal_time=signal_time, gross_r=net_r, fees_r=0, slippage_r=0, funding_r=0,
        net_r=net_r, entry_price=100, exit_price=100 + net_r, stop_loss=99, target_price=110,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
    )


class TestRollingPerformanceMonitor:
    def test_less_than_n_trades(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(5)]
        rpm = RollingPerformanceMonitor(trades)
        r = rpm.rolling_expectancy(10)
        assert len(r) == 0

    def test_rolling_expectancy_correct(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(15)]
        rpm = RollingPerformanceMonitor(trades)
        r = rpm.rolling_expectancy(10)
        assert len(r) == 6
        assert r[0]["value"] == 1.0

    def test_latest_no_data(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(5)]
        rpm = RollingPerformanceMonitor(trades)
        latest = rpm.latest()
        assert latest["sufficient_data"] is False

    def test_latest_with_data(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(20)]
        rpm = RollingPerformanceMonitor(trades)
        latest = rpm.latest()
        assert latest["sufficient_data"] is True
        assert latest["rolling_10_ev"] == 1.0

    def test_rolling_drawdown(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", 2.0, t0),
            make_trade("t2", -3.0, t0 + timedelta(hours=1)),
            make_trade("t3", 1.0, t0 + timedelta(hours=2)),
        ]
        rpm = RollingPerformanceMonitor(trades)
        dd = rpm.rolling_drawdown()
        assert len(dd) == 3
        assert dd[1]["drawdown_r"] > 0

    def test_only_past_trades_used(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0 if i < 10 else -1.0, t0 + timedelta(hours=i)) for i in range(20)]
        rpm = RollingPerformanceMonitor(trades)
        r = rpm.rolling_expectancy(10)
        assert len(r) == 11
        # First 10 windows all have EV 1.0 (only winners), later windows mix
        assert r[0]["value"] == 1.0
