from datetime import datetime

from ultimate_trader.historical_replay.models import HistoricalCandle, TradeDirection
from ultimate_trader.strategy_engine.filters import (
    ALL_FILTERS,
    FundingFilter,
    FvgFilter,
    OrderBlockFilter,
    OrderflowFilter,
    RiskFilter,
    SessionFilter,
    StructureFilter,
    SweepFilter,
    TrendFilter,
    VolatilityFilter,
    VolumeFilter,
)
from ultimate_trader.strategy_engine.models import StrategyConfig, StrategyContext


def make_candle(close: float = 100.0, high: float = 101.0, low: float = 99.0, vol: float = 1000.0) -> HistoricalCandle:
    return HistoricalCandle(
        symbol="BTCUSDT", timeframe="15m", timestamp=datetime(2024, 1, 1, 12, 0),
        open=close, high=high, low=low, close=close, volume=vol,
    )


def make_context(
    candles: list[HistoricalCandle] | None = None,
    direction: TradeDirection = TradeDirection.LONG,
    **kwargs,
) -> StrategyContext:
    candle = candles[-1] if candles else make_candle()
    return StrategyContext(
        candle=candle,
        candles_history=candles or [candle],
        direction=direction,
        **kwargs,
    )


class TestTrendFilter:
    def test_returns_data_unavailable_when_few_candles(self):
        ctx = make_context([make_candle(100.0) for _ in range(5)])
        config = StrategyConfig()
        result = TrendFilter().evaluate(ctx, config)
        assert not result.data_available
        assert result.score == 0.0
        assert not result.passed

    def test_strong_bullish_alignment(self):
        closes = [100.0 + i * 0.5 for i in range(220)]
        candles = [make_candle(c, c + 1, c - 1) for c in closes]
        ctx = make_context(candles, TradeDirection.LONG)
        config = StrategyConfig(ema_periods=[20, 50, 100])
        result = TrendFilter().evaluate(ctx, config)
        assert result.passed
        assert result.score >= 80.0

    def test_strong_bearish_alignment(self):
        closes = [200.0 - i * 0.5 for i in range(220)]
        candles = [make_candle(c, c + 1, c - 1) for c in closes]
        ctx = make_context(candles, TradeDirection.SHORT)
        config = StrategyConfig(ema_periods=[20, 50, 100])
        result = TrendFilter().evaluate(ctx, config)
        assert result.passed
        assert result.score >= 80.0

    def test_opposing_trend_drops_score(self):
        closes = [100.0 - i * 0.3 for i in range(220)]
        candles = [make_candle(c, c + 1, c - 1) for c in closes]
        ctx = make_context(candles, TradeDirection.LONG)
        config = StrategyConfig(ema_periods=[20, 50])
        result = TrendFilter().evaluate(ctx, config)
        assert not result.passed


class TestStructureFilter:
    def test_no_structure_events(self):
        ctx = make_context()
        result = StructureFilter().evaluate(ctx, StrategyConfig())
        assert result.data_available is False
        assert result.score == 50.0

    def test_aligned_structure(self):
        event = type("Event", (), {"direction": "BULLISH", "structure_type": "BOS", "index": 10})
        ctx = make_context(lsm_structure_events=[event])
        result = StructureFilter().evaluate(ctx, StrategyConfig())
        assert result.passed
        assert result.score >= 80.0

    def test_opposing_structure(self):
        event = type("Event", (), {"direction": "BEARISH", "structure_type": "CHOCH", "index": 10})
        ctx = make_context(lsm_structure_events=[event])
        result = StructureFilter().evaluate(ctx, StrategyConfig())
        assert not result.passed


class TestSweepFilter:
    def test_no_sweeps(self):
        ctx = make_context()
        result = SweepFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available
        assert result.score == 50.0

    def test_matching_sweep(self):
        sweep = type("Sweep", (), {"sweep_type": "BUY_SIDE_SWEEP", "has_reclaim": True, "index": 99})
        ctx = make_context(candles=[make_candle() for _ in range(100)], lsm_sweeps=[sweep])
        result = SweepFilter().evaluate(ctx, StrategyConfig())
        assert result.passed

    def test_opposing_sweep(self):
        sweep = type("Sweep", (), {"sweep_type": "BUY_SIDE_SWEEP", "has_reclaim": True, "index": 99})
        ctx = make_context(candles=[make_candle() for _ in range(100)], lsm_sweeps=[sweep], direction=TradeDirection.SHORT)
        result = SweepFilter().evaluate(ctx, StrategyConfig())
        assert not result.passed


class TestFvgFilter:
    def test_no_fvgs(self):
        ctx = make_context()
        result = FvgFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available

    def test_matching_fvg(self):
        fvg = type("FVG", (), {"fvg_type": "BULLISH_FVG", "is_mitigated": False, "is_filled": False, "index": 99})
        ctx = make_context(candles=[make_candle() for _ in range(100)], lsm_fvgs=[fvg])
        result = FvgFilter().evaluate(ctx, StrategyConfig())
        assert result.passed

    def test_opposing_fvg(self):
        fvg = type("FVG", (), {"fvg_type": "BULLISH_FVG", "is_mitigated": False, "is_filled": False, "index": 99})
        ctx = make_context(candles=[make_candle() for _ in range(100)], lsm_fvgs=[fvg], direction=TradeDirection.SHORT)
        result = FvgFilter().evaluate(ctx, StrategyConfig())
        assert not result.passed


class TestOrderBlockFilter:
    def test_no_obs(self):
        ctx = make_context()
        result = OrderBlockFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available

    def test_matching_ob(self):
        ob = type("OB", (), {"ob_type": "BULLISH_OB", "is_mitigated": False, "is_invalidated": False, "strength_score": 60, "index": 10})
        ctx = make_context(lsm_order_blocks=[ob])
        result = OrderBlockFilter().evaluate(ctx, StrategyConfig())
        assert result.passed


class TestVolumeFilter:
    def test_not_enough_data(self):
        ctx = make_context(candles=[make_candle() for _ in range(3)])
        result = VolumeFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available

    def test_strong_volume(self):
        candles = [make_candle(vol=100.0) for _ in range(20)]
        candles.append(make_candle(vol=5000.0))
        ctx = make_context(candles)
        result = VolumeFilter().evaluate(ctx, StrategyConfig(min_volume_ratio=0.8, volume_lookback=20))
        assert result.passed
        assert result.score >= 80.0

    def test_low_volume(self):
        candles = [make_candle(vol=100.0) for _ in range(25)]
        candles.append(make_candle(vol=30.0))
        ctx = make_context(candles)
        result = VolumeFilter().evaluate(ctx, StrategyConfig(min_volume_ratio=0.8, volume_lookback=20))
        assert not result.passed


class TestOrderflowFilter:
    def test_no_data(self):
        ctx = make_context()
        result = OrderflowFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available
        assert result.score == 50.0

    def test_with_data(self):
        ctx = make_context(orderflow_data={"some": "data"})
        result = OrderflowFilter().evaluate(ctx, StrategyConfig())
        assert result.data_available
        assert result.score == 50.0


class TestFundingFilter:
    def test_no_data(self):
        ctx = make_context()
        result = FundingFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available

    def test_favorable_for_long(self):
        ctx = make_context(funding_rate=-0.0002)
        result = FundingFilter().evaluate(ctx, StrategyConfig())
        assert result.passed

    def test_unfavorable_for_long(self):
        ctx = make_context(funding_rate=0.0005)
        result = FundingFilter().evaluate(ctx, StrategyConfig())
        assert not result.passed


class TestOpenInterestFilter:
    def test_no_data(self):
        from ultimate_trader.strategy_engine.filters import OpenInterestFilter as OIFilter
        ctx = make_context()
        result = OIFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available

    def test_with_data(self):
        from ultimate_trader.strategy_engine.filters import OpenInterestFilter as OIFilter
        ctx = make_context(open_interest=100000.0)
        result = OIFilter().evaluate(ctx, StrategyConfig())
        assert result.data_available
        assert result.score == 50.0


class TestSessionFilter:
    def test_weekday_session(self):
        ctx = make_context()
        result = SessionFilter().evaluate(ctx, StrategyConfig(session_allowed=True))
        assert result.passed
        assert 50.0 <= result.score <= 100.0


class TestVolatilityFilter:
    def test_not_enough_data(self):
        ctx = make_context(candles=[make_candle() for _ in range(5)])
        result = VolatilityFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available

    def test_ideal_volatility(self):
        candles = [make_candle(100.0, 101.0, 99.0) for _ in range(20)]
        ctx = make_context(candles)
        result = VolatilityFilter().evaluate(ctx, StrategyConfig(atr_min_mult=0.3, atr_max_mult=4.0))
        assert result.passed

    def test_too_low_volatility(self):
        candles = [
            make_candle(close=100.0 + i * 5.0, high=110.0 + i * 5.0, low=90.0 + i * 5.0) for i in range(15)
        ]
        candles.append(make_candle(close=175.0, high=175.01, low=174.99))
        ctx = make_context(candles)
        result = VolatilityFilter().evaluate(ctx, StrategyConfig(atr_min_mult=0.5, atr_max_mult=4.0))
        assert not result.passed


class TestRiskFilter:
    def test_no_stop(self):
        ctx = make_context(stop_loss=0.0)
        result = RiskFilter().evaluate(ctx, StrategyConfig())
        assert not result.data_available

    def test_small_risk(self):
        ctx = make_context(entry_price=100.0, stop_loss=99.0)
        result = RiskFilter().evaluate(ctx, StrategyConfig(max_risk_percent=2.0))
        assert result.passed
        assert result.score >= 80.0

    def test_excessive_risk(self):
        ctx = make_context(entry_price=100.0, stop_loss=85.0)
        result = RiskFilter().evaluate(ctx, StrategyConfig(max_risk_percent=2.0))
        assert not result.passed


class TestAllFilters:
    def test_twelve_filters_loaded(self):
        assert len(ALL_FILTERS) == 12

    def test_each_filter_has_name(self):
        for f in ALL_FILTERS:
            assert hasattr(f, "name")
            assert f.name

    def test_each_filter_evaluate_returns_filter_result(self):
        from ultimate_trader.strategy_engine.models import FilterResult
        candle = make_candle()
        ctx = StrategyContext(candle=candle, candles_history=[candle])
        config = StrategyConfig()
        for f in ALL_FILTERS:
            result = f.evaluate(ctx, config)
            assert isinstance(result, FilterResult)
