from datetime import datetime

from ultimate_trader.backtest_forensics.overtrading_detector import OvertradingDetector
from ultimate_trader.backtest_forensics.trade_diagnostics import (
    ExitReason,
    TradeDiagnostics,
    TradeDirection,
)


def make_td(day: int = 1, hour: int = 8, direction: str = "LONG") -> TradeDiagnostics:
    return TradeDiagnostics(
        trade_id=f"T-{day}-{hour}",
        symbol="BTCUSDT",
        direction=TradeDirection(direction),
        signal_time=datetime(2024, 1, day, hour, 0),
        entry_price=100.0, stop_loss=99.0, target_price=106.0,
        exit_price=103.0, exit_reason=ExitReason.TAKE_PROFIT,
        net_r=1.0, gross_r=1.0, fees_r=0, slippage_r=0,
        holding_candles=5, candles_until_exit=5,
        max_favorable_excursion_r=1.5, max_adverse_excursion_r=0.2,
        entry_to_stop_distance_percent=1.0, entry_to_target_distance_percent=3.0,
        rr_ratio=3.0,
    )


class TestOvertradingDetector:
    def test_no_trades(self):
        result = OvertradingDetector().analyze([])
        assert result.total_trades == 0
        assert not result.overtrading_warning

    def test_few_trades_no_warning(self):
        trades = [make_td(day=1, hour=8), make_td(day=1, hour=12)]
        result = OvertradingDetector().analyze(trades)
        assert not result.overtrading_warning

    def test_overtrading_above_4_flagged(self):
        trades = [make_td(day=1, hour=i) for i in range(6)]
        result = OvertradingDetector().analyze(trades)
        assert result.overtrading_warning
        assert result.max_trades_in_day >= 6
        assert not result.severe_overtrading_warning

    def test_severe_overtrading_above_10_flagged(self):
        trades = [make_td(day=1, hour=i) for i in range(12)]
        result = OvertradingDetector().analyze(trades)
        assert result.severe_overtrading_warning
        assert result.max_trades_in_day >= 12

    def test_repeated_direction_detected(self):
        trades = [make_td(day=1, hour=i, direction="LONG") for i in range(5)]
        result = OvertradingDetector().analyze(trades)
        assert result.repeated_direction_trades >= 4

    def test_signal_clusters_detected(self):
        trades = [make_td(day=1, hour=i) for i in range(5)]
        result = OvertradingDetector().analyze(trades)
        assert len(result.signal_clusters) >= 1
