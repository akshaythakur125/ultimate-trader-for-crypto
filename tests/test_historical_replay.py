from datetime import datetime

from ultimate_trader.historical_replay.data_loader import HistoricalDataLoader
from ultimate_trader.historical_replay.models import (
    ExitReason,
    HistoricalCandle,
    ReplayConclusion,
    ReplayConfig,
    ReplayTrade,
    TradeDirection,
    TradePlan,
)
from ultimate_trader.historical_replay.replay_report import ReplayReport
from ultimate_trader.historical_replay.metrics import ReplayMetrics
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator


class TestHistoricalReplay:
    def test_historical_candle_model(self):
        c = HistoricalCandle(
            symbol="BTCUSDT", timeframe="1h", timestamp=datetime.utcnow(),
            open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0,
        )
        assert c.symbol == "BTCUSDT"
        assert c.close == 100.5

    def test_trade_plan_model(self):
        p = TradePlan(
            plan_id="TP-001", symbol="BTCUSDT", direction=TradeDirection.LONG,
            signal_time=datetime.utcnow(), entry_zone_high=101.0, entry_zone_low=99.0,
            stop_loss=98.0, target_price=105.0,
        )
        assert p.direction == TradeDirection.LONG
        assert p.target_price == 105.0

    def test_replay_trade_model(self):
        t = ReplayTrade(
            trade_id="RT-001", symbol="BTCUSDT", direction=TradeDirection.SHORT,
            signal_time=datetime.utcnow(), entry_price=100.0, exit_price=99.0,
            stop_loss=101.0, target_price=98.0, gross_r=1.0, net_r=0.95,
            exit_reason=ExitReason.TAKE_PROFIT, holding_candles=5,
        )
        assert t.direction == TradeDirection.SHORT
        assert t.net_r == 0.95

    def test_replay_config_defaults(self):
        cfg = ReplayConfig()
        assert cfg.confluence_score_threshold == 30.0
        assert cfg.min_rr == 3.0
        assert cfg.max_risk_score == 50.0
        assert cfg.warmup_candles == 50
        assert cfg.taker_fee_percent == 0.04
        assert cfg.slippage_percent == 0.02

    def test_replay_conclusion_values(self):
        assert ReplayConclusion.EDGE_DETECTED.value == "EDGE_DETECTED"
        assert ReplayConclusion.NO_EDGE.value == "NO_EDGE"
        assert ReplayConclusion.INSUFFICIENT_DATA.value == "INSUFFICIENT_DATA"
        assert ReplayConclusion.NEEDS_MORE_TESTING.value == "NEEDS_MORE_TESTING"

    def test_replay_report_insufficient_data(self):
        metrics = ReplayMetrics(total_signals=0, rejected_signals=0)
        report = ReplayReport.build(
            report_id="RR-TEST", symbol="BTCUSDT", timeframe="1h",
            start_time=datetime.utcnow(), end_time=datetime.utcnow(),
            candles_processed=100, metrics=metrics, trades=[],
            rejected_summary=[], engine_skip_summary=[],
        )
        assert report.final_conclusion == ReplayConclusion.INSUFFICIENT_DATA

    def test_replay_report_no_edge_when_all_rejected(self):
        metrics = ReplayMetrics(total_signals=5, rejected_signals=5)
        report = ReplayReport.build(
            report_id="RR-TEST", symbol="BTCUSDT", timeframe="1h",
            start_time=datetime.utcnow(), end_time=datetime.utcnow(),
            candles_processed=100, metrics=metrics, trades=[],
            rejected_summary=[{"timestamp": "t", "reason": "r"}],
            engine_skip_summary=[],
        )
        assert report.final_conclusion == ReplayConclusion.NO_EDGE

    def test_replay_report_needs_more_testing_few_trades(self):
        metrics = ReplayMetrics(total_signals=3, rejected_signals=0, executed_trades=3)
        report = ReplayReport.build(
            report_id="RR-TEST", symbol="BTCUSDT", timeframe="1h",
            start_time=datetime.utcnow(), end_time=datetime.utcnow(),
            candles_processed=100, metrics=metrics, trades=[],
            rejected_summary=[], engine_skip_summary=[],
        )
        assert report.final_conclusion == ReplayConclusion.NEEDS_MORE_TESTING
