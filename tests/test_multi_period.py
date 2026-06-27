import pytest
from datetime import datetime, timedelta
from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig
from ultimate_trader.robustness_lab import FrozenConfig, MultiPeriodReplay, PeriodResult


class TestMultiPeriodReplay:
    def test_empty(self):
        frozen = FrozenConfig()
        rcfg = ReplayConfig(warmup_candles=50, taker_fee_percent=0.04, slippage_percent=0.02, funding_per_candle_percent=0.001)
        mp = MultiPeriodReplay(frozen, rcfg)
        assert mp.results == []

    def test_period_result_defaults(self):
        pr = PeriodResult(label="test", start="2024-01-01", end="2024-01-31", candles=500, total_trades=5, win_rate=0.6, expectancy=0.5, profit_factor=1.5, avg_trades_per_day=2.0, max_drawdown=1.0)
        assert pr.label == "test"
        assert pr.verdict == ""

    def test_data_not_available(self):
        frozen = FrozenConfig()
        mp = MultiPeriodReplay(frozen)
        assert mp.results == []

    def test_period_result_verdict_insufficient(self):
        pr = PeriodResult(label="test", start="2024-01-01", end="2024-01-31", candles=100, total_trades=3, win_rate=0.6, expectancy=0.5, profit_factor=1.5, avg_trades_per_day=1.0, max_drawdown=0.5)
        mp = MultiPeriodReplay(FrozenConfig())
        verdict = mp._verdict(pr)
        assert verdict == "INSUFFICIENT_TRADES"

    def test_period_result_verdict_edge(self):
        pr = PeriodResult(label="test", start="2024-01-01", end="2024-01-31", candles=500, total_trades=20, win_rate=0.55, expectancy=0.6, profit_factor=1.5, avg_trades_per_day=2.0, max_drawdown=1.0)
        mp = MultiPeriodReplay(FrozenConfig())
        verdict = mp._verdict(pr)
        assert verdict == "EDGE"

    def test_period_result_verdict_weak_edge(self):
        pr = PeriodResult(label="test", start="2024-01-01", end="2024-01-31", candles=500, total_trades=20, win_rate=0.45, expectancy=0.2, profit_factor=1.1, avg_trades_per_day=2.0, max_drawdown=1.0)
        mp = MultiPeriodReplay(FrozenConfig())
        verdict = mp._verdict(pr)
        assert verdict == "WEAK_EDGE"

    def test_period_result_verdict_no_edge(self):
        pr = PeriodResult(label="test", start="2024-01-01", end="2024-01-31", candles=500, total_trades=20, win_rate=0.4, expectancy=-0.1, profit_factor=0.9, avg_trades_per_day=2.0, max_drawdown=1.0)
        mp = MultiPeriodReplay(FrozenConfig())
        verdict = mp._verdict(pr)
        assert verdict == "NO_EDGE"

    def test_str_repr(self):
        pr = PeriodResult(label="test", start="2024-01-01", end="2024-01-31", candles=500, total_trades=5, win_rate=0.6, expectancy=0.5, profit_factor=1.5, avg_trades_per_day=2.0, max_drawdown=1.0)
        s = str(pr)
        assert "test" in s
        assert "5" in s
