from datetime import datetime

from ultimate_trader.historical_replay.metrics import ReplayMetrics
from ultimate_trader.historical_replay.models import (
    ExitReason,
    ReplayTrade,
    TradeDirection,
)


def make_trade(net_r: float, holding: int = 5) -> ReplayTrade:
    return ReplayTrade(
        trade_id=f"RT-{net_r}", symbol="BTCUSDT", direction=TradeDirection.LONG,
        signal_time=datetime.utcnow(), entry_price=100.0,
        stop_loss=99.0, target_price=106.0, gross_r=net_r, net_r=net_r,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
        holding_candles=holding,
    )


class TestReplayMetrics:
    def test_empty_metrics(self):
        m = ReplayMetrics.calculate([], 0, 0)
        assert m.executed_trades == 0
        assert m.win_rate == 0.0

    def test_all_wins_metrics(self):
        trades = [make_trade(2.0), make_trade(1.5), make_trade(3.0)]
        m = ReplayMetrics.calculate(trades, 5, 2)
        assert m.executed_trades == 3
        assert m.win_rate == 1.0
        assert m.average_r > 0
        assert m.profit_factor > 0
        assert m.max_consecutive_losses == 0

    def test_all_losses_metrics(self):
        trades = [make_trade(-1.0), make_trade(-1.5), make_trade(-2.0)]
        m = ReplayMetrics.calculate(trades, 3, 0)
        assert m.executed_trades == 3
        assert m.win_rate == 0.0
        assert m.average_r < 0

    def test_mixed_results(self):
        trades = [make_trade(3.0), make_trade(-1.0), make_trade(2.0), make_trade(-1.5)]
        m = ReplayMetrics.calculate(trades, 6, 2)
        assert m.executed_trades == 4
        assert m.win_rate == 0.5
        assert m.average_r > 0
        assert m.profit_factor > 1.0
        assert m.signal_to_trade_conversion_rate > 0

    def test_max_consecutive_losses(self):
        trades = [
            make_trade(2.0), make_trade(-1.0), make_trade(-1.0),
            make_trade(-1.0), make_trade(3.0), make_trade(-2.0),
        ]
        m = ReplayMetrics.calculate(trades, 6, 0)
        assert m.max_consecutive_losses == 3

    def test_best_and_worst_trade(self):
        trades = [make_trade(5.0), make_trade(-3.0), make_trade(2.0)]
        m = ReplayMetrics.calculate(trades, 3, 0)
        assert m.best_trade_r == 5.0
        assert m.worst_trade_r == -3.0

    def test_max_drawdown(self):
        trades = [make_trade(3.0), make_trade(-2.0), make_trade(1.0), make_trade(-4.0)]
        m = ReplayMetrics.calculate(trades, 4, 0)
        assert m.max_drawdown_r > 0

    def test_average_holding_time(self):
        trades = [make_trade(1.0, holding=10), make_trade(2.0, holding=20)]
        m = ReplayMetrics.calculate(trades, 2, 0)
        assert m.average_holding_time == 15.0

    def test_rejection_rate(self):
        trades = [make_trade(1.0)]
        m = ReplayMetrics.calculate(trades, 10, 5)
        assert m.rejected_signals == 5
        assert m.rejection_rate == 0.5
        assert m.signal_to_trade_conversion_rate == 0.2
