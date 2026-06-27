from datetime import datetime

from ultimate_trader.backtest_forensics.outcome_analyzer import OutcomeAnalyzer
from ultimate_trader.backtest_forensics.trade_diagnostics import (
    ExitReason,
    TradeDiagnostics,
    TradeDirection,
)


def make_td(
    net_r: float = 1.0,
    exit_reason: str = "TAKE_PROFIT",
    holding_candles: int = 5,
    max_mfe: float = 1.5,
    max_mae: float = 0.3,
    rr: float = 3.0,
    target_price: float = 103.0,
) -> TradeDiagnostics:
    return TradeDiagnostics(
        trade_id="T1",
        symbol="BTCUSDT",
        direction=TradeDirection.LONG,
        signal_time=datetime(2024, 1, 1, 12, 0),
        entry_time=datetime(2024, 1, 1, 12, 15),
        exit_time=datetime(2024, 1, 1, 13, 30),
        entry_price=100.0,
        stop_loss=99.0,
        target_price=target_price,
        exit_price=103.0,
        exit_reason=ExitReason(exit_reason),
        net_r=net_r,
        gross_r=net_r + 0.1,
        fees_r=0.05,
        slippage_r=0.05,
        holding_candles=holding_candles,
        candles_until_exit=holding_candles,
        max_favorable_excursion_r=max_mfe,
        max_adverse_excursion_r=max_mae,
        entry_to_stop_distance_percent=1.0,
        entry_to_target_distance_percent=3.0,
        rr_ratio=rr,
        signal_quality_grade="GOOD",
        confidence_score=75.0,
        filters_passed=["trend", "volume"],
        filters_failed=[],
    )


class TestOutcomeAnalyzer:
    def test_empty_trades(self):
        stats = OutcomeAnalyzer().analyze([])
        assert stats.total_trades == 0
        assert stats.win_rate == 0.0

    def test_all_wins(self):
        trades = [make_td(net_r=2.0), make_td(net_r=1.5)]
        stats = OutcomeAnalyzer().analyze(trades)
        assert stats.total_trades == 2
        assert stats.win_rate == 100.0
        assert stats.avg_r == 1.75

    def test_all_losses(self):
        trades = [make_td(net_r=-1.0, exit_reason="STOP_LOSS"), make_td(net_r=-0.5, exit_reason="STOP_LOSS")]
        stats = OutcomeAnalyzer().analyze(trades)
        assert stats.total_trades == 2
        assert stats.win_rate == 0.0
        assert stats.avg_r == -0.75

    def test_mixed_results(self):
        trades = [
            make_td(net_r=2.0, exit_reason="TAKE_PROFIT", holding_candles=5),
            make_td(net_r=-1.0, exit_reason="STOP_LOSS", holding_candles=1),
        ]
        stats = OutcomeAnalyzer().analyze(trades)
        assert stats.total_trades == 2
        assert stats.win_rate == 50.0
        assert stats.avg_r == 0.5

    def test_stopped_within_1_candle_detected(self):
        trades = [
            make_td(net_r=-1.0, exit_reason="STOP_LOSS", holding_candles=1),
            make_td(net_r=2.0, exit_reason="TAKE_PROFIT", holding_candles=10),
        ]
        stats = OutcomeAnalyzer().analyze(trades)
        assert stats.stopped_within_1_candle == 1
        assert stats.stopped_within_1_candle_pct == 50.0

    def test_same_candle_stop_first_detected(self):
        trades = [
            make_td(net_r=-1.0, exit_reason="STOP_LOSS", holding_candles=1),
            make_td(net_r=2.0, exit_reason="TAKE_PROFIT", holding_candles=3),
        ]
        stats = OutcomeAnalyzer().analyze(trades)
        assert stats.same_candle_stop_first == 1

    def test_reached_1r_but_stopped(self):
        trades = [
            make_td(net_r=-1.0, exit_reason="STOP_LOSS", max_mfe=1.5, holding_candles=5),
        ]
        stats = OutcomeAnalyzer().analyze(trades)
        assert stats.reached_1r_mfe_but_stopped == 1

    def test_outcome_statistics_types(self):
        trades = [make_td(), make_td(net_r=-1.0, exit_reason="STOP_LOSS")]
        stats = OutcomeAnalyzer().analyze(trades)
        assert isinstance(stats.win_rate, float)
        assert isinstance(stats.avg_r, float)
        assert isinstance(stats.stopped_within_1_candle_pct, float)
