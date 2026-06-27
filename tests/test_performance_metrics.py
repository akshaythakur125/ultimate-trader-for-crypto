from datetime import datetime

import pytest

from ultimate_trader.validation_lab.performance_metrics import (
    Direction,
    ExitReason,
    PerformanceMetrics,
    TradeResult,
)


def make_trade(trade_id: str, net_r: float, gross_r: float = 0.0):
    return TradeResult(
        trade_id=trade_id,
        hypothesis_id="RH-TEST",
        symbol="BTCUSDT",
        entry_time=datetime(2024, 1, 1),
        exit_time=datetime(2024, 1, 2),
        direction=Direction.LONG,
        entry_price=100.0,
        exit_price=100.0 + gross_r,
        gross_r=gross_r,
        net_r=net_r,
        exit_reason=ExitReason.TAKE_PROFIT,
    )


class TestPerformanceMetrics:
    def test_empty_trades(self):
        metrics = PerformanceMetrics.calculate([])
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0

    def test_all_wins(self):
        trades = [
            make_trade("T1", 2.0, 2.5),
            make_trade("T2", 1.5, 2.0),
        ]
        metrics = PerformanceMetrics.calculate(trades)
        assert metrics.total_trades == 2
        assert metrics.wins == 2
        assert metrics.losses == 0
        assert metrics.win_rate == 1.0

    def test_all_losses(self):
        trades = [
            make_trade("T1", -1.0, -1.2),
            make_trade("T2", -2.0, -2.5),
        ]
        metrics = PerformanceMetrics.calculate(trades)
        assert metrics.wins == 0
        assert metrics.losses == 2

    def test_mixed_performance(self):
        trades = [
            make_trade("T1", 2.0, 2.5),
            make_trade("T2", -1.0, -1.2),
        ]
        metrics = PerformanceMetrics.calculate(trades)
        assert metrics.win_rate == 0.5
        assert metrics.expectancy_r > 0

    def test_profit_factor(self):
        trades = [
            make_trade("T1", 3.0, 3.5),
            make_trade("T2", -1.0, -1.2),
        ]
        metrics = PerformanceMetrics.calculate(trades)
        assert metrics.profit_factor == 3.0

    def test_max_drawdown(self):
        trades = [
            make_trade("T1", 5.0, 5.5),
            make_trade("T2", -3.0, -3.5),
            make_trade("T3", 2.0, 2.5),
        ]
        metrics = PerformanceMetrics.calculate(trades)
        assert metrics.max_drawdown_r > 0

    def test_consecutive_losses(self):
        trades = [
            make_trade("T1", -1.0, -1.2),
            make_trade("T2", -2.0, -2.5),
            make_trade("T3", 3.0, 3.5),
            make_trade("T4", -1.5, -2.0),
            make_trade("T5", -1.0, -1.5),
        ]
        metrics = PerformanceMetrics.calculate(trades)
        assert metrics.consecutive_losses_max == 2

    def test_false_signal_rate(self):
        trades = [
            make_trade("T1", -3.0, -3.5),
            make_trade("T2", -5.0, -6.0),
            make_trade("T3", 2.0, 2.5),
        ]
        metrics = PerformanceMetrics.calculate(trades)
        assert metrics.false_signal_rate > 0
