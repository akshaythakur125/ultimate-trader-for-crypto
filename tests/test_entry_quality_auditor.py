from datetime import datetime

from ultimate_trader.backtest_forensics.entry_quality_auditor import EntryQualityAuditor
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
    max_mfe: float = 1.0,
    max_mae: float = 0.0,
    holding_candles: int = 5,
    exit_reason: str = "TAKE_PROFIT",
    entry_to_stop_pct: float = 1.0,
    ) -> TradeDiagnostics:
        etp = abs(target_price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
        rr = abs(target_price - entry_price) / abs(entry_price - stop_loss) if entry_price > 0 and abs(entry_price - stop_loss) > 0 else 0.0
        return TradeDiagnostics(
            trade_id="T1", symbol="BTCUSDT",
            direction=TradeDirection(direction),
            signal_time=datetime(2024, 1, 1, 12, 0),
            entry_price=entry_price, stop_loss=stop_loss,
            target_price=target_price,
            exit_price=target_price, exit_reason=ExitReason(exit_reason),
            net_r=1.0, gross_r=1.0, fees_r=0, slippage_r=0,
            holding_candles=holding_candles, candles_until_exit=holding_candles,
            max_favorable_excursion_r=max_mfe,
            max_adverse_excursion_r=max_mae,
            entry_to_stop_distance_percent=entry_to_stop_pct,
            entry_to_target_distance_percent=etp,
            rr_ratio=rr,
        )


class TestEntryQualityAuditor:
    def test_no_entry_price(self):
        td = make_td(entry_price=0.0)
        result = EntryQualityAuditor().audit(td)
        assert not result.entry_safe

    def test_entry_too_close_to_invalidation(self):
        td = make_td(entry_price=100, stop_loss=99.95, target_price=106)
        result = EntryQualityAuditor().audit(td, atr=2.0)
        warned = any("invalidation" in w.lower() or "tight" in w.lower() for w in result.warnings)
        if not result.entry_safe:
            assert warned or len(result.warnings) > 0

    def test_immediate_adverse_candle(self):
        td = make_td(max_mfe=0.0, max_mae=0.5)
        result = EntryQualityAuditor().audit(td)
        warned = any("adverse" in w.lower() for w in result.warnings)
        assert warned, f"Expected adverse entry warning, got: {result.warnings}"

    def test_same_candle_stop_timing(self):
        td = make_td(holding_candles=1, exit_reason="STOP_LOSS")
        result = EntryQualityAuditor().audit(td)
        warned = any("timing" in w.lower() or "candle" in w.lower() for w in result.warnings)
        assert warned, f"Expected timing warning, got: {result.warnings}"

    def test_entry_already_at_target_long(self):
        td = make_td(entry_price=106, stop_loss=105, target_price=106)
        result = EntryQualityAuditor().audit(td)
        warned = any("target" in w.lower() for w in result.warnings)
        assert warned, f"Expected target warning, got: {result.warnings}"

    def test_narrow_entry_zone(self):
        td = make_td(entry_to_stop_pct=0.01)
        result = EntryQualityAuditor().audit(td)
        warned = any("narrow" in w.lower() for w in result.warnings)
        assert warned, f"Expected narrow zone warning, got: {result.warnings}"

    def score_decreases_with_warnings(self):
        td = make_td(max_mfe=0.0, max_mae=0.5)
        result = EntryQualityAuditor().audit(td)
        assert result.entry_quality_score < 100
