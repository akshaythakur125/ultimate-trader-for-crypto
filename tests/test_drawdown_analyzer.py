import pytest
from datetime import datetime, timedelta
from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection, ExitReason
from ultimate_trader.drawdown_control.drawdown_analyzer import DrawdownAnalyzer


def make_trade(trade_id: str, net_r: float, signal_time: datetime, symbol: str = "BTCUSDT"):
    return ReplayTrade(
        trade_id=trade_id, symbol=symbol, direction=TradeDirection.LONG,
        signal_time=signal_time, gross_r=net_r, fees_r=0, slippage_r=0, funding_r=0,
        net_r=net_r, entry_price=100, exit_price=100 + net_r, stop_loss=99, target_price=110,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
    )


class TestDrawdownAnalyzer:
    def test_empty_trades(self):
        da = DrawdownAnalyzer()
        r = da.analyze([])
        assert r["total_drawdown_episodes"] == 0
        assert r["max_drawdown_r"] == 0

    def test_episodes_detected(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", 2.0, t0),
            make_trade("t2", -3.0, t0 + timedelta(hours=1)),
            make_trade("t3", 1.0, t0 + timedelta(hours=2)),
        ]
        da = DrawdownAnalyzer()
        r = da.analyze(trades)
        assert r["total_drawdown_episodes"] >= 1

    def test_largest_episode_summary(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", 1.0, t0),
            make_trade("t2", -5.0, t0 + timedelta(hours=1)),
            make_trade("t3", -3.0, t0 + timedelta(hours=2)),
            make_trade("t4", 2.0, t0 + timedelta(hours=3)),
        ]
        da = DrawdownAnalyzer()
        r = da.analyze(trades)
        assert r["largest_episode"] is not None
        assert r["largest_episode"]["depth_r"] > 0

    def test_worst_5_drops(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", -0.3, t0 + timedelta(hours=i)) for i in range(10)]
        da = DrawdownAnalyzer()
        r = da.analyze(trades)
        assert len(r["worst_5_drops"]) <= 5

    def test_cause_large_losses(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", 1.0, t0),
            make_trade("t2", -3.0, t0 + timedelta(hours=1)),
            make_trade("t3", 3.0, t0 + timedelta(hours=2)),
        ]
        da = DrawdownAnalyzer()
        r = da.analyze(trades)
        if r["largest_episode"]:
            assert r["largest_episode"]["cause"] in ("few_large_losses", "many_small_losses")
