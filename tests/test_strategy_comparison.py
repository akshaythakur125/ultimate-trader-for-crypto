from datetime import datetime

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig
from ultimate_trader.strategy_engine.comparison import _compute_metrics, run_comparison
from ultimate_trader.strategy_engine.models import ComparisonResult, StrategyConfig


def make_trade(pnl: float, r_multiple: float = 0.0):
    return type("Trade", (), {"pnl": pnl, "r_multiple": r_multiple})()


class TestComputeMetrics:
    def test_empty_trades(self):
        m = _compute_metrics([])
        assert m["total_trades"] == 0.0
        assert m["win_rate"] == 0.0
        assert m["expectancy"] == 0.0

    def test_all_wins(self):
        trades = [make_trade(100.0, 2.0), make_trade(50.0, 1.0)]
        m = _compute_metrics(trades)
        assert m["total_trades"] == 2.0
        assert m["win_rate"] == 100.0
        assert m["expectancy"] == 1.5

    def test_all_losses(self):
        trades = [make_trade(-100.0, -1.0), make_trade(-50.0, -0.5)]
        m = _compute_metrics(trades)
        assert m["win_rate"] == 0.0
        assert m["expectancy"] == -0.75

    def test_mixed_results(self):
        trades = [make_trade(100.0, 2.0), make_trade(-50.0, -1.0)]
        m = _compute_metrics(trades)
        assert m["total_trades"] == 2.0
        assert m["win_rate"] == 50.0
        assert m["profit_factor"] == 2.0


class TestRunComparison:
    def test_empty_candles_returns_comparison_result(self):
        result = run_comparison(
            candles=[],
            lsm_data_provider=lambda c, i: {},
        )
        assert isinstance(result, ComparisonResult)
        assert result.old_trades == 0
        assert result.new_trades == 0

    def test_small_candle_set_no_errors(self):
        candles = [
            HistoricalCandle(
                symbol="BTCUSDT", timeframe="15m", timestamp=datetime(2024, 1, 1, i, 0),
                open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0,
            )
            for i in range(5)
        ]
        result = run_comparison(
            candles=candles,
            lsm_data_provider=lambda c, i: {},
            config=StrategyConfig(confidence_threshold=100.0),
            old_replay_config=ReplayConfig(warmup_candles=1),
            new_replay_config=ReplayConfig(warmup_candles=1),
        )
        assert isinstance(result, ComparisonResult)
