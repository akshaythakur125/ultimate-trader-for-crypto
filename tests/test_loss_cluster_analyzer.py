import pytest
from datetime import datetime, timedelta
from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection, ExitReason
from ultimate_trader.drawdown_control.loss_cluster_analyzer import LossClusterAnalyzer


def make_trade(trade_id: str, net_r: float, signal_time: datetime, symbol: str = "BTCUSDT", direction: TradeDirection = TradeDirection.LONG):
    return ReplayTrade(
        trade_id=trade_id, symbol=symbol, direction=direction,
        signal_time=signal_time, gross_r=net_r, fees_r=0, slippage_r=0, funding_r=0,
        net_r=net_r, entry_price=100, exit_price=100 + net_r, stop_loss=99, target_price=110,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
    )


class TestLossClusterAnalyzer:
    def test_no_losses(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(5)]
        lca = LossClusterAnalyzer()
        r = lca.analyze(trades)
        assert r["max_consecutive_losses"] == 0

    def test_consecutive_losses_detected(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", -1.0, t0),
            make_trade("t2", -1.0, t0 + timedelta(hours=1)),
            make_trade("t3", -1.0, t0 + timedelta(hours=2)),
            make_trade("t4", 1.0, t0 + timedelta(hours=3)),
        ]
        lca = LossClusterAnalyzer()
        r = lca.analyze(trades)
        assert r["max_consecutive_losses"] >= 3

    def test_loss_clusters_by_symbol(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", -1.0, t0, "ETHUSDT"),
            make_trade("t2", -1.0, t0 + timedelta(hours=1), "ETHUSDT"),
            make_trade("t3", -1.0, t0 + timedelta(hours=2), "SOLUSDT"),
            make_trade("t4", 1.0, t0 + timedelta(hours=3), "BTCUSDT"),
        ]
        lca = LossClusterAnalyzer()
        r = lca.analyze(trades)
        assert "ETHUSDT" in r["symbol_loss_summary"]

    def test_worst_day_detected(self):
        t0 = datetime(2024, 1, 1)
        t1 = datetime(2024, 1, 2)
        trades = [
            make_trade("t1", -2.0, t0),
            make_trade("t2", -2.0, t0 + timedelta(hours=1)),
            make_trade("t3", 1.0, t1),
        ]
        lca = LossClusterAnalyzer()
        r = lca.analyze(trades)
        assert r["daily_loss_summary"]["worst_day"] == t0.strftime("%Y-%m-%d")

    def test_severe_clusters(self):
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", -1.5, t0),
            make_trade("t2", -1.5, t0 + timedelta(hours=1)),
            make_trade("t3", 1.0, t0 + timedelta(hours=2)),
        ]
        lca = LossClusterAnalyzer()
        r = lca.analyze(trades)
        assert len(r["severe_clusters"]) >= 0
