from datetime import datetime

from ultimate_trader.backtest_forensics.failure_classifier import (
    FailureCategory,
    FailureClassifier,
)
from ultimate_trader.backtest_forensics.trade_diagnostics import (
    ExitReason,
    TradeDiagnostics,
    TradeDirection,
)


def make_td(
    net_r: float = -1.0,
    exit_reason: str = "STOP_LOSS",
    holding_candles: int = 3,
    max_mfe: float = 0.0,
    max_mae: float = 0.5,
    entry_to_stop_pct: float = 1.0,
    entry_price: float = 100.0,
    stop_loss: float = 99.0,
    target_price: float = 106.0,
    rr: float = 3.0,
) -> TradeDiagnostics:
    return TradeDiagnostics(
        trade_id="T1", symbol="BTCUSDT",
        direction=TradeDirection.LONG,
        signal_time=datetime(2024, 1, 1, 12, 0),
        entry_price=entry_price, stop_loss=stop_loss,
        target_price=target_price,
        exit_price=stop_loss, exit_reason=ExitReason(exit_reason),
        net_r=net_r, gross_r=net_r, fees_r=0, slippage_r=0,
        holding_candles=holding_candles, candles_until_exit=holding_candles,
        max_favorable_excursion_r=max_mfe,
        max_adverse_excursion_r=max_mae,
        entry_to_stop_distance_percent=entry_to_stop_pct,
        entry_to_target_distance_percent=abs(target_price - entry_price) / entry_price * 100,
        rr_ratio=rr,
    )


class TestFailureClassifier:
    def test_long_winning_trade_not_failure(self):
        td = make_td(net_r=2.0, exit_reason="TAKE_PROFIT")
        result = FailureClassifier().classify(td)
        assert result.category != FailureCategory.UNKNOWN  # winners still classified

    def test_short_winning_trade_not_failure(self):
        td = make_td(net_r=2.0, exit_reason="TAKE_PROFIT")
        td.direction = TradeDirection.SHORT
        result = FailureClassifier().classify(td)
        assert result.category != FailureCategory.UNKNOWN

    def test_same_candle_stop_first_detected(self):
        td = make_td(exit_reason="STOP_LOSS", holding_candles=1)
        result = FailureClassifier().classify(td)
        assert result.category == FailureCategory.SAME_CANDLE_STOP_FIRST

    def test_simulator_logic_issue_0_holding(self):
        td = make_td(exit_reason="STOP_LOSS", holding_candles=0)
        result = FailureClassifier().classify(td)
        assert result.category == FailureCategory.SIMULATOR_LOGIC_ISSUE

    def test_bad_entry_adverse_immediate(self):
        td = make_td(max_mfe=0.0, max_mae=0.5)
        result = FailureClassifier().classify(td)
        assert result.category == FailureCategory.BAD_ENTRY

    def test_target_too_ambitious(self):
        td = make_td(max_mfe=1.5, net_r=-1.0)
        result = FailureClassifier().classify(td)
        assert result.category == FailureCategory.TARGET_TOO_AMBITIOUS

    def test_stop_too_tight(self):
        td = make_td(entry_to_stop_pct=0.01, entry_price=100, stop_loss=99.99)
        result = FailureClassifier().classify(td)
        assert result.category == FailureCategory.STOP_TOO_TIGHT

    def test_expiry_classified_as_chop(self):
        td = make_td(exit_reason="EXPIRY")
        result = FailureClassifier().classify(td)
        assert result.category == FailureCategory.CHOP_MARKET

    def test_all_categories_have_explanation(self):
        td = make_td()
        result = FailureClassifier().classify(td)
        assert len(result.explanation) > 0
        assert len(result.fix_suggestion) > 0
