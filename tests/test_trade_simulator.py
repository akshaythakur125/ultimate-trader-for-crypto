from datetime import datetime, timedelta

from ultimate_trader.historical_replay.models import (
    ExitReason,
    HistoricalCandle,
    ReplayConfig,
    TradeDirection,
    TradePlan,
)
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator


def make_candle(ts: datetime, open_p: float, high: float, low: float, close: float) -> HistoricalCandle:
    return HistoricalCandle(
        symbol="BTCUSDT", timeframe="1h", timestamp=ts,
        open=open_p, high=high, low=low, close=close, volume=100.0,
    )


class TestTradeSimulator:
    def test_long_win(self):
        config = ReplayConfig(taker_fee_percent=0.0, slippage_percent=0.0, funding_per_candle_percent=0.0)
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-1", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=98.0, target_price=106.0,
        )
        candle1 = make_candle(datetime(2024, 1, 1, 1), 100, 102, 99, 101)
        sim.process_candle(candle1, [plan])
        candle2 = make_candle(datetime(2024, 1, 1, 2), 105, 107, 104, 106)
        results = sim.process_candle(candle2, [])
        assert len(results) >= 1
        win_trades = [t for t in results if t.net_r > 0]
        assert len(win_trades) >= 1

    def test_short_win(self):
        config = ReplayConfig(taker_fee_percent=0.0, slippage_percent=0.0, funding_per_candle_percent=0.0)
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-2", symbol="BTCUSDT", direction=TradeDirection.SHORT,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=102.0, target_price=95.0,
        )
        candle1 = make_candle(datetime(2024, 1, 1, 1), 100, 100, 94, 95.5)
        results = sim.process_candle(candle1, [plan])
        win_trades = [t for t in results if t.net_r > 0]
        assert len(win_trades) >= 1

    def test_stop_first_when_both_hit_same_candle_long(self):
        config = ReplayConfig(taker_fee_percent=0.0, slippage_percent=0.0, funding_per_candle_percent=0.0)
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-3", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=99.5, target_price=106.0,
        )
        candle = make_candle(datetime(2024, 1, 1, 1), 100, 107, 99, 105)
        results = sim.process_candle(candle, [plan])
        exited = [t for t in results if t.exit_reason == ExitReason.STOP_LOSS]
        assert len(exited) >= 1

    def test_stop_first_when_both_hit_same_candle_short(self):
        config = ReplayConfig(taker_fee_percent=0.0, slippage_percent=0.0, funding_per_candle_percent=0.0)
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-4", symbol="BTCUSDT", direction=TradeDirection.SHORT,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=101.5, target_price=93.0,
        )
        candle = make_candle(datetime(2024, 1, 1, 1), 100, 104, 92, 95)
        results = sim.process_candle(candle, [plan])
        exited = [t for t in results if t.exit_reason == ExitReason.STOP_LOSS]
        assert len(exited) >= 1

    def test_expiry(self):
        config = ReplayConfig(taker_fee_percent=0.0, slippage_percent=0.0, funding_per_candle_percent=0.0)
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-5", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=80.0, target_price=200.0,
        )
        candle1 = make_candle(datetime(2024, 1, 1), 100, 100.5, 99.5, 100)
        sim.process_candle(candle1, [plan])
        for i in range(62):
            c = make_candle(datetime(2024, 1, 1) + timedelta(hours=1 + i), 100, 101, 99, 100)
            sim.process_candle(c, [])
        assert len(sim.completed_trades) >= 1
        assert sim.completed_trades[-1].exit_reason == ExitReason.MAX_HOLDING_TIME

    def test_fees_slippage_reduce_net_r(self):
        config = ReplayConfig(
            taker_fee_percent=0.04, slippage_percent=0.02,
            funding_per_candle_percent=0.001, min_rr=3.0,
        )
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-6", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=98.0, target_price=110.0,
        )
        candle = make_candle(datetime(2024, 1, 1, 1), 100, 111, 99, 110)
        results = sim.process_candle(candle, [plan])
        for t in results:
            if t.exit_reason == ExitReason.TAKE_PROFIT:
                assert t.net_r < t.gross_r
                assert t.fees_r > 0
                assert t.slippage_r > 0

    def test_no_entry_when_candle_outside_zone(self):
        config = ReplayConfig()
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-7", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=105.0, entry_zone_low=104.0,
            stop_loss=103.0, target_price=110.0,
        )
        candle = make_candle(datetime(2024, 1, 1, 1), 100, 101, 99, 100)
        results = sim.process_candle(candle, [plan])
        assert len(results) == 0

    def test_active_trades_property(self):
        config = ReplayConfig()
        sim = TradeSimulator(config)
        plan = TradePlan(
            plan_id="TP-8", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime(2024, 1, 1, 0), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=80.0, target_price=200.0,
        )
        candle = make_candle(datetime(2024, 1, 1, 1), 100, 100.5, 99.5, 100)
        sim.process_candle(candle, [plan])
        assert len(sim.active_trades) >= 1
