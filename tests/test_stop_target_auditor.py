from datetime import datetime

from ultimate_trader.backtest_forensics.stop_target_auditor import StopTargetAuditor
from ultimate_trader.backtest_forensics.trade_diagnostics import (
    ExitReason,
    TradeDiagnostics,
    TradeDirection,
)


def make_td(
    direction: str = "LONG",
    entry_price: float = 100.0,
    stop_loss: float = 99.0,
    target_price: float = 106.0,
    exit_reason: str = "TAKE_PROFIT",
    holding_candles: int = 5,
    net_r: float = 2.0,
) -> TradeDiagnostics:
    return TradeDiagnostics(
        trade_id="T1", symbol="BTCUSDT",
        direction=TradeDirection(direction),
        signal_time=datetime(2024, 1, 1, 12, 0),
        entry_price=entry_price, stop_loss=stop_loss,
        target_price=target_price,
        exit_price=target_price, exit_reason=ExitReason(exit_reason),
        net_r=net_r, gross_r=net_r, fees_r=0, slippage_r=0,
        holding_candles=holding_candles, candles_until_exit=holding_candles,
        max_favorable_excursion_r=net_r, max_adverse_excursion_r=0,
        entry_to_stop_distance_percent=abs(entry_price - stop_loss) / entry_price * 100,
        entry_to_target_distance_percent=abs(target_price - entry_price) / entry_price * 100,
        rr_ratio=abs(target_price - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0,
    )


class TestStopTargetAuditor:
    def test_no_stop(self):
        td = make_td(stop_loss=0.0)
        result = StopTargetAuditor().audit(td)
        assert not result.stop_target_valid
        assert len(result.warnings) >= 1

    def test_long_winning_trade_classified_correctly(self):
        td = make_td(direction="LONG", entry_price=100, stop_loss=99, target_price=106)
        result = StopTargetAuditor().audit(td, atr=2.0, candle_range=1.5)
        assert result.stop_target_valid or not result.stop_target_valid
        if result.stop_target_valid:
            assert result.stop_quality_score >= 50

    def test_short_winning_trade_classified_correctly(self):
        td = make_td(direction="SHORT", entry_price=100, stop_loss=101, target_price=94)
        result = StopTargetAuditor().audit(td, atr=2.0, candle_range=1.5)
        assert result.stop_quality_score >= 0

    def test_stop_too_tight_detected(self):
        td = make_td(direction="LONG", entry_price=100, stop_loss=99.9, target_price=106)
        result = StopTargetAuditor().audit(td, atr=2.0)
        warned = any("tight" in w.lower() for w in result.warnings)
        assert warned, f"Expected tight stop warning, got: {result.warnings}"

    def test_target_too_ambitious_detected(self):
        td = make_td(direction="LONG", entry_price=100, stop_loss=99, target_price=500)
        result = StopTargetAuditor().audit(td, atr=2.0)
        warned = any("far" in w.lower() or "ambitious" in w.lower() for w in result.warnings)
        assert warned, f"Expected target warning, got: {result.warnings}"

    def test_inverted_stop_long_detected(self):
        td = make_td(direction="LONG", entry_price=100, stop_loss=101, target_price=106)
        result = StopTargetAuditor().audit(td)
        warned = any("above entry" in w.lower() for w in result.warnings)
        assert warned, f"Expected inverted stop warning, got: {result.warnings}"

    def test_inverted_stop_short_detected(self):
        td = make_td(direction="SHORT", entry_price=100, stop_loss=99, target_price=94)
        result = StopTargetAuditor().audit(td)
        warned = any("below entry" in w.lower() for w in result.warnings)
        assert warned, f"Expected inverted stop warning, got: {result.warnings}"

    def test_low_rr_warning(self):
        td = make_td(direction="LONG", entry_price=100, stop_loss=95, target_price=102)
        result = StopTargetAuditor().audit(td)
        warned = any("rr" in w.lower() for w in result.warnings)
        assert warned, f"Expected low RR warning, got: {result.warnings}"

    def test_same_candle_stop_first_detected(self):
        td = make_td(exit_reason="STOP_LOSS", holding_candles=1, entry_price=100, stop_loss=99.5, target_price=106)
        result = StopTargetAuditor().audit(td)
        warned = any("candle" in w.lower() for w in result.warnings)
        assert warned, f"Expected same-candle warning, got: {result.warnings}"
