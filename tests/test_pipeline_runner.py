from datetime import datetime
from typing import Any

from ultimate_trader.historical_replay.models import (
    HistoricalCandle,
    ReplayConfig,
    TradeDirection,
)
from ultimate_trader.historical_replay.pipeline_runner import ReplayPipelineRunner
from ultimate_trader.historical_replay.replay_journal import ReplayJournal


def make_candle(ts: datetime, close: float) -> HistoricalCandle:
    return HistoricalCandle(
        symbol="BTCUSDT", timeframe="1h", timestamp=ts,
        open=close, high=close + 1, low=close - 1, close=close, volume=100.0,
    )


def make_mock_lsm(permission: str = "ALLOW", score: float = 60.0, bias: str = "LONG") -> dict[str, Any]:
    class MockSwing:
        def add_candle(self, c): pass
        def get_swing_highs(self): return []
        def get_swing_lows(self): return []
        def get_equal_highs(self): return []
        def get_equal_lows(self): return []

    class MockPool:
        def analyze(self, *a, **kw): return []

    class MockSweep:
        def analyze(self, *a, **kw): return []

    class MockStruct:
        def analyze(self, *a, **kw): return []

    class MockFVG:
        def analyze(self, *a, **kw): return []

    class MockOB:
        def analyze(self, *a, **kw): return []

    class MockPD:
        def analyze(self, *a, **kw): return None

    class MockDisp:
        def analyze(self, *a, **kw): return None

    class MockConf:
        def analyze(self, *a, **kw):
            from ultimate_trader.liquidity_smart_money.models import ConfluenceResult, DirectionalBias
            return ConfluenceResult(
                confluence_score=score,
                directional_bias=DirectionalBias(bias),
                trade_permission=permission,
            )

    class MockLSM:
        def get(self, name):
            m = {
                "swing_detector": MockSwing(),
                "liquidity_pool_detector": MockPool(),
                "sweep_detector": MockSweep(),
                "market_structure_engine": MockStruct(),
                "fair_value_gap_detector": MockFVG(),
                "order_block_detector": MockOB(),
                "premium_discount_engine": MockPD(),
                "displacement_engine": MockDisp(),
                "confluence_engine": MockConf(),
            }
            return m.get(name)

    return MockLSM()


class TestReplayPipelineRunner:
    def test_skips_engines_when_not_provided(self):
        journal = ReplayJournal()
        runner = ReplayPipelineRunner(ReplayConfig(), journal)
        candle = make_candle(datetime(2024, 1, 1, 0), 100.0)
        plan = runner.run_candle(candle, 0)
        assert plan is None
        assert journal.total_engine_skips >= 5

    def test_generates_plan_with_lsm_allowed(self):
        journal = ReplayJournal()
        lsm = make_mock_lsm("ALLOW", 50.0, "LONG")
        runner = ReplayPipelineRunner(ReplayConfig(), journal, liquidity_smart_money=lsm)
        candle = make_candle(datetime(2024, 1, 1, 0), 100.0)
        plan = runner.run_candle(candle, 0)
        assert plan is not None
        assert plan.direction == TradeDirection.LONG

    def test_rejects_plan_with_block_trade(self):
        journal = ReplayJournal()
        lsm = make_mock_lsm("BLOCK", 60.0, "LONG")
        runner = ReplayPipelineRunner(ReplayConfig(), journal, liquidity_smart_money=lsm)
        candle = make_candle(datetime(2024, 1, 1, 0), 100.0)
        plan = runner.run_candle(candle, 0)
        assert plan is None

    def test_rejects_plan_below_threshold(self):
        journal = ReplayJournal()
        lsm = make_mock_lsm("ALLOW", 10.0, "LONG")
        config = ReplayConfig(confluence_score_threshold=30.0)
        runner = ReplayPipelineRunner(config, journal, liquidity_smart_money=lsm)
        candle = make_candle(datetime(2024, 1, 1, 0), 100.0)
        plan = runner.run_candle(candle, 0)
        assert plan is None

    def test_pending_plans_accumulate(self):
        journal = ReplayJournal()
        lsm = make_mock_lsm("ALLOW", 50.0, "LONG")
        runner = ReplayPipelineRunner(ReplayConfig(), journal, liquidity_smart_money=lsm)
        for i in range(3):
            c = make_candle(datetime(2024, 1, 1, i), 100.0 + i)
            runner.run_candle(c, i)
        assert len(runner.pending_plans) >= 1

    def test_resets_pending_plans(self):
        journal = ReplayJournal()
        lsm = make_mock_lsm("ALLOW", 50.0, "LONG")
        runner = ReplayPipelineRunner(ReplayConfig(), journal, liquidity_smart_money=lsm)
        candle = make_candle(datetime(2024, 1, 1, 0), 100.0)
        runner.run_candle(candle, 0)
        assert len(runner.pending_plans) >= 1
        runner.reset()
        assert len(runner.pending_plans) == 0
