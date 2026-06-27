import pytest
from datetime import datetime, timedelta
from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection, ExitReason
from ultimate_trader.drawdown_control.equity_curve import EquityCurve


def make_trade(trade_id: str, net_r: float, signal_time: datetime, symbol: str = "BTCUSDT"):
    return ReplayTrade(
        trade_id=trade_id, symbol=symbol, direction=TradeDirection.LONG,
        signal_time=signal_time, gross_r=net_r, fees_r=0, slippage_r=0, funding_r=0,
        net_r=net_r, entry_price=100, exit_price=100 + net_r, stop_loss=99, target_price=110,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
    )


class TestEquityCurve:
    def test_empty_trades(self):
        ec = EquityCurve([])
        assert ec.total_r == 0
        assert ec.max_drawdown_r == 0

    def test_all_wins_no_drawdown(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(5)]
        ec = EquityCurve(trades)
        assert ec.max_drawdown_r == 0
        assert ec.total_r == 5.0

    def test_max_drawdown_calculated(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", 2.0, t0),
            make_trade("t2", -3.0, t0 + timedelta(hours=1)),
            make_trade("t3", -2.0, t0 + timedelta(hours=2)),
            make_trade("t4", 4.0, t0 + timedelta(hours=3)),
        ]
        ec = EquityCurve(trades)
        assert ec.max_drawdown_r > 0

    def test_episodes_detected(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", 2.0, t0),
            make_trade("t2", -3.0, t0 + timedelta(hours=1)),
            make_trade("t3", 1.0, t0 + timedelta(hours=2)),
        ]
        ec = EquityCurve(trades)
        assert len(ec.episodes) > 0

    def test_worst_5_drops(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", -0.5, t0 + timedelta(hours=i)) for i in range(10)]
        ec = EquityCurve(trades)
        assert len(ec.worst_5_drops) <= 5

    def test_underwater_periods(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", -1.0, t0),
            make_trade("t2", -1.0, t0 + timedelta(hours=1)),
            make_trade("t3", 3.0, t0 + timedelta(hours=2)),
        ]
        ec = EquityCurve(trades)
        assert len(ec.underwater_periods) > 0
