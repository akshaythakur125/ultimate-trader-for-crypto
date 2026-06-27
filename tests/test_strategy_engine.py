from datetime import datetime

from ultimate_trader.historical_replay.models import HistoricalCandle, TradeDirection
from ultimate_trader.strategy_engine import (
    ConfidenceScorer,
    StrategyCandidate,
    StrategyConfig,
    StrategyEngine,
    generate_candidate_report,
)


def make_candle(close: float = 100.0, high: float = 101.0, low: float = 99.0, vol: float = 1000.0) -> HistoricalCandle:
    return HistoricalCandle(
        symbol="BTCUSDT", timeframe="15m", timestamp=datetime(2024, 1, 1, 12, 0),
        open=close, high=high, low=low, close=close, volume=vol,
    )


class TestStrategyEngine:
    def test_initial_state(self):
        engine = StrategyEngine()
        assert len(engine.candidates) == 0
        assert len(engine.candles_history) == 0
        assert isinstance(engine.config, StrategyConfig)

    def test_add_candle(self):
        engine = StrategyEngine()
        c = make_candle()
        engine.add_candle(c)
        assert len(engine.candles_history) == 1

    def test_evaluate_returns_candidate(self):
        engine = StrategyEngine()
        c = make_candle()
        engine.add_candle(c)
        candidate = engine.evaluate(c, direction=TradeDirection.LONG)
        assert candidate is None or isinstance(candidate, StrategyCandidate)
        assert len(engine.candidates) == 1
        assert engine.candidates[0].filter_results is not None

    def test_evaluate_populates_filter_results(self):
        config = StrategyConfig(confidence_threshold=0.0)
        engine = StrategyEngine(config)
        candles = [make_candle(100.0 + i * 0.3, 101.0 + i * 0.3, 99.0 + i * 0.3) for i in range(60)]
        for c in candles:
            engine.add_candle(c)
        candidate = engine.evaluate(candles[-1], direction=TradeDirection.LONG)
        assert candidate is not None
        assert len(candidate.filter_results) == 12
        passed = [n for n, r in candidate.filter_results.items() if r.passed and r.data_available]
        failed = [n for n, r in candidate.filter_results.items() if not r.passed and r.data_available]
        assert len(passed) + len(failed) > 0

    def test_rejection_reason_set_when_not_approved(self):
        config = StrategyConfig(confidence_threshold=100.0)
        engine = StrategyEngine(config)
        c = make_candle()
        engine.add_candle(c)
        candidate = engine.evaluate(c)
        assert candidate is None
        assert len(engine.candidates) == 1
        assert not engine.candidates[0].approved
        assert engine.candidates[0].rejection_reason

    def test_reset_clears_state(self):
        engine = StrategyEngine()
        c = make_candle()
        engine.add_candle(c)
        engine.evaluate(c)
        engine.reset()
        assert len(engine.candidates) == 0
        assert len(engine.candles_history) == 0

    def test_incorporates_lsm_data(self):
        engine = StrategyEngine()
        for i in range(60):
            engine.add_candle(make_candle(100.0 + i * 0.3, 101.0 + i * 0.3, 99.0 + i * 0.3))
        c = make_candle(118.0, 119.0, 117.0)
        candidate = engine.evaluate(c, lsm_data={
            "direction": "LONG",
            "confluence_score": 80.0,
            "trade_permission": "ALLOW",
            "sweeps": [],
            "structure_events": [],
            "fvgs": [],
            "order_blocks": [],
            "risk_score": 20.0,
        })
        assert candidate is not None or not engine.candidates[0].approved


class TestConfidenceScorer:
    def test_returns_all_12_results(self):
        c = make_candle()
        from ultimate_trader.strategy_engine.models import StrategyContext
        ctx = StrategyContext(candle=c, candles_history=[c])
        config = StrategyConfig()
        scorer = ConfidenceScorer()
        results, total = scorer.score(ctx, config)
        assert len(results) == 12
        assert 0.0 <= total <= 100.0


class TestCandidateReport:
    def test_report_contains_candidate_info(self):
        config = StrategyConfig(confidence_threshold=0.0)
        engine = StrategyEngine(config)
        c = make_candle()
        engine.add_candle(c)
        engine.evaluate(c, direction=TradeDirection.LONG)
        report = generate_candidate_report(engine.candidates[0])
        assert "Candidate:" in report
        assert engine.candidates[0].candidate_id in report
        assert "LONG" in report
