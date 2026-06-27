from datetime import datetime

from ultimate_trader.historical_replay.models import (
    ExitReason,
    HistoricalCandle,
    ReplayConfig,
    ReplayTrade,
    TradeDirection,
)
from ultimate_trader.historical_replay.parameter_sweeper import ParameterSweeper


def demo_run_trades(config: ReplayConfig) -> list[ReplayTrade]:
    return [
        ReplayTrade(
            trade_id="RT-1", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime.utcnow(), entry_price=100.0, exit_price=106.0,
            stop_loss=99.0, target_price=106.0, gross_r=5.0, net_r=4.8,
            exit_reason=ExitReason.TAKE_PROFIT, holding_candles=3,
        ),
        ReplayTrade(
            trade_id="RT-2", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime.utcnow(), entry_price=100.0, exit_price=98.0,
            stop_loss=99.0, target_price=106.0, gross_r=-1.0, net_r=-1.1,
            exit_reason=ExitReason.STOP_LOSS, holding_candles=4,
        ),
        ReplayTrade(
            trade_id="RT-3", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime.utcnow(), entry_price=100.0, exit_price=99.0,
            stop_loss=99.0, target_price=106.0, gross_r=-0.5, net_r=-0.6,
            exit_reason=ExitReason.STOP_LOSS, holding_candles=2,
        ),
    ]


class TestParameterSweeper:
    def test_sweep_ranks_results(self):
        sweeper = ParameterSweeper()
        base = ReplayConfig()
        grid = {"min_rr": [2.0, 3.0], "confluence_score_threshold": [20.0, 30.0]}
        report = sweeper.sweep(base, grid, demo_run_trades)
        assert len(report.results) == 4
        assert report.best_result is not None
        assert any(r.score > 0 for r in report.results)

    def test_single_parameter_sweep(self):
        sweeper = ParameterSweeper()
        base = ReplayConfig()
        grid = {"min_rr": [1.0, 2.0, 3.0]}
        report = sweeper.sweep(base, grid, demo_run_trades)
        assert len(report.results) == 3

    def test_best_result_ranked_first(self):
        sweeper = ParameterSweeper()
        base = ReplayConfig()
        grid = {"min_rr": [1.0, 10.0]}
        report = sweeper.sweep(base, grid, demo_run_trades)
        assert report.results[0].score >= report.results[1].score

    def test_empty_grid(self):
        sweeper = ParameterSweeper()
        base = ReplayConfig()
        report = sweeper.sweep(base, {}, demo_run_trades)
        assert len(report.results) == 1

    def test_no_trades_penalty(self):
        def empty_run(_cfg):
            return []

        sweeper = ParameterSweeper()
        base = ReplayConfig()
        grid = {"min_rr": [1.0, 2.0]}
        report = sweeper.sweep(base, grid, empty_run)
        for r in report.results:
            assert r.score == 0.0
