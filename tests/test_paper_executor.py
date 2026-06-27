import uuid

import pytest

from ultimate_trader.paper_trading.account import PaperAccount
from ultimate_trader.paper_trading.executor import PaperTradeExecutor
from ultimate_trader.paper_trading.order import OrderSide, OrderStatus
from ultimate_trader.signal_engine import (
    DirectionBias,
    EntryType,
    EntryZone,
    FinalRecommendation,
    PositionSizingSuggestion,
    SignalContext,
    SignalGateResult,
    SignalReport,
    TradePlan,
    TradeStatus,
)


def make_report(
    recommendation: FinalRecommendation = FinalRecommendation.PAPER_TRADE_CANDIDATE,
    direction: DirectionBias = DirectionBias.LONG,
    entry_type: EntryType = EntryType.LIMIT_ZONE,
) -> SignalReport:
    ctx = SignalContext(
        context_id="CTX-TEST",
        symbol="BTCUSDT",
        timeframe="1h",
        validated_hypothesis_id="HYP-TEST",
        direction_bias=direction,
        current_price=100.0,
        confidence_score=70.0,
        risk_score=20.0,
        uncertainty_score=15.0,
        expected_value_r=4.0,
        validation_passed=True,
        volatility_score=25.0,
    )
    ez = EntryZone(
        entry_zone_id="EZ-TEST",
        symbol="BTCUSDT",
        direction=direction,
        entry_min=99.0,
        entry_max=101.0,
        preferred_entry=100.0,
        entry_type=entry_type,
    )
    tp = TradePlan(
        trade_plan_id="TP-TEST",
        symbol="BTCUSDT",
        direction=direction,
        timeframe="1h",
        entry_zone=ez,
        position_sizing=PositionSizingSuggestion(
            sizing_id="SZ-TEST",
            suggested_risk_percent=1.0,
            position_size_units=1.0,
        ),
        trade_status=TradeStatus.READY_FOR_PAPER_TRADE,
    )
    gate = SignalGateResult(
        approved_for_alert=True,
        approved_for_paper_trade=True,
        approved_for_live_trade=False,
        checks_passed=5,
        checks_failed=0,
        message="All checks passed",
    )
    return SignalReport(
        report_id=f"SR-{uuid.uuid4().hex[:8].upper()}",
        signal_context=ctx,
        trade_plan=tp,
        signal_gate=gate,
        final_recommendation=recommendation,
        explanation="Test signal",
    )


class TestPaperTradeExecutorInit:
    def test_default_initialization(self):
        ex = PaperTradeExecutor()
        assert isinstance(ex.account, PaperAccount)
        assert ex.default_quantity == 0.01
        assert len(ex._executed_signals) == 0

    def test_custom_account(self):
        acc = PaperAccount(starting_balance=50000.0)
        ex = PaperTradeExecutor(account=acc)
        assert ex.account.starting_balance == 50000.0


class TestPaperTradeExecutorEvaluate:
    def test_evaluate_paper_trade_candidate(self):
        ex = PaperTradeExecutor()
        report = make_report(FinalRecommendation.PAPER_TRADE_CANDIDATE)
        order = ex.evaluate(report)
        assert order is not None
        assert order.symbol == "BTCUSDT"
        assert order.quantity == 1.0
        assert order.price == 100.0

    def test_evaluate_reject_signal(self):
        ex = PaperTradeExecutor()
        report = make_report(FinalRecommendation.REJECT_SIGNAL)
        order = ex.evaluate(report)
        assert order is None

    def test_evaluate_no_safe_entry(self):
        ex = PaperTradeExecutor()
        report = make_report(FinalRecommendation.NO_SAFE_ENTRY)
        order = ex.evaluate(report)
        assert order is None

    def test_evaluate_human_review(self):
        ex = PaperTradeExecutor()
        report = make_report(FinalRecommendation.HUMAN_REVIEW)
        order = ex.evaluate(report)
        assert order is None

    def test_evaluate_wait_for_entry(self):
        ex = PaperTradeExecutor()
        report = make_report(FinalRecommendation.WAIT_FOR_ENTRY)
        order = ex.evaluate(report)
        assert order is None

    def test_evaluate_alert_only(self):
        ex = PaperTradeExecutor()
        report = make_report(FinalRecommendation.ALERT_ONLY)
        order = ex.evaluate(report)
        assert order is None

    def test_deduplicate_same_report_id(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order1 = ex.evaluate(report)
        order2 = ex.evaluate(report)
        assert order1 is not None
        assert order2 is None

    def test_evaluate_no_entry_zone(self):
        ex = PaperTradeExecutor()
        ctx = SignalContext(
            context_id="CTX-TEST", symbol="BTCUSDT", timeframe="1h",
            validated_hypothesis_id="HYP-TEST", direction_bias=DirectionBias.LONG,
            current_price=100.0, confidence_score=70.0, risk_score=20.0,
            uncertainty_score=15.0, expected_value_r=4.0, validation_passed=True,
            volatility_score=25.0,
        )
        tp = TradePlan(
            trade_plan_id="TP-TEST", symbol="BTCUSDT",
            direction=DirectionBias.LONG, timeframe="1h",
        )
        report = SignalReport(
            report_id="SR-NO-EZ", signal_context=ctx, trade_plan=tp,
            final_recommendation=FinalRecommendation.PAPER_TRADE_CANDIDATE,
        )
        order = ex.evaluate(report)
        assert order is None


class TestPaperTradeExecutorFillOrder:
    def test_fill_order_success(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order = ex.evaluate(report)
        order.status = OrderStatus.SUBMITTED
        position = ex.fill_order(order, fill_price=100.5)
        assert position is not None
        assert position.symbol == "BTCUSDT"
        assert position.entry_price == 100.5
        assert position.quantity == 1.0
        assert position.side == OrderSide.BUY
        assert order.status == OrderStatus.FILLED
        assert len(order.fills) == 1

    def test_fill_order_wrong_status(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order = ex.evaluate(report)
        order.status = OrderStatus.FILLED
        position = ex.fill_order(order, fill_price=100.5)
        assert position is None

    def test_fill_order_partial(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order = ex.evaluate(report)
        order.status = OrderStatus.SUBMITTED
        position = ex.fill_order(order, fill_price=100.0, fill_quantity=0.5)
        assert position is not None
        assert position.quantity == 0.5
        assert order.filled_quantity == 0.5


class TestPaperTradeExecutorClosePosition:
    def test_close_position_profitable(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order = ex.evaluate(report)
        order.status = OrderStatus.SUBMITTED
        position = ex.fill_order(order, fill_price=100.0)
        trade = ex.close_position(position, exit_price=110.0, exit_reason="target_hit")
        assert trade is not None
        assert trade.gross_pnl == 10.0
        assert trade.net_pnl > 0
        assert trade.exit_reason == "target_hit"
        assert ex.account.total_pnl > 0

    def test_close_position_loss(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order = ex.evaluate(report)
        order.status = OrderStatus.SUBMITTED
        position = ex.fill_order(order, fill_price=100.0)
        trade = ex.close_position(position, exit_price=90.0, exit_reason="stop_hit")
        assert trade is not None
        assert trade.gross_pnl == -10.0
        assert trade.net_pnl < 0
        assert ex.account.total_pnl < 0

    def test_close_position_already_closed(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order = ex.evaluate(report)
        order.status = OrderStatus.SUBMITTED
        position = ex.fill_order(order, fill_price=100.0)
        position.current_price = 110.0
        trade1 = ex.close_position(position, exit_price=110.0)
        trade2 = ex.close_position(position, exit_price=110.0)
        assert trade1 is not None
        assert trade2 is None, "Position should be closed after first close"

    def test_close_position_updates_account(self):
        ex = PaperTradeExecutor()
        report = make_report()
        order = ex.evaluate(report)
        order.status = OrderStatus.SUBMITTED
        position = ex.fill_order(order, fill_price=100.0)
        ex.close_position(position, exit_price=105.0, exit_reason="target_hit")
        assert len(ex.account.closed_trades) == 1
        assert len(ex.account.positions) == 0
        assert ex.account.total_pnl > 0


class TestPaperTradeExecutorShort:
    def test_short_signal_creates_sell_order(self):
        ex = PaperTradeExecutor()
        report = make_report(direction=DirectionBias.SHORT)
        order = ex.evaluate(report)
        assert order is not None
        assert order.side == OrderSide.SELL

    def test_short_position_close(self):
        ex = PaperTradeExecutor()
        report = make_report(direction=DirectionBias.SHORT)
        order = ex.evaluate(report)
        order.status = OrderStatus.SUBMITTED
        position = ex.fill_order(order, fill_price=100.0)
        assert position.side == OrderSide.SELL
        ex.close_position(position, exit_price=90.0, exit_reason="target_hit")
        assert ex.account.total_pnl > 0


class TestPaperTradeExecutorSizing:
    def test_uses_default_quantity_when_no_sizing(self):
        ex = PaperTradeExecutor(default_quantity=0.05)
        ctx = SignalContext(
            context_id="CTX-TEST", symbol="BTCUSDT", timeframe="1h",
            validated_hypothesis_id="HYP-TEST", direction_bias=DirectionBias.LONG,
            current_price=100.0, confidence_score=70.0, risk_score=20.0,
            uncertainty_score=15.0, expected_value_r=4.0, validation_passed=True,
            volatility_score=25.0,
        )
        tp = TradePlan(
            trade_plan_id="TP-TEST", symbol="BTCUSDT",
            direction=DirectionBias.LONG, timeframe="1h",
            entry_zone=EntryZone(
                entry_zone_id="EZ-TEST", symbol="BTCUSDT",
                direction=DirectionBias.LONG,
                preferred_entry=100.0, entry_type=EntryType.LIMIT_ZONE,
            ),
        )
        report = SignalReport(
            report_id="SR-NO-SIZE", signal_context=ctx, trade_plan=tp,
            final_recommendation=FinalRecommendation.PAPER_TRADE_CANDIDATE,
        )
        order = ex.evaluate(report)
        assert order is not None
        assert order.quantity == 0.05


class TestPaperTradeExecutorReportObject:
    def test_model_fields(self):
        report = make_report()
        assert hasattr(report, "report_id")
        assert hasattr(report, "final_recommendation")
        assert hasattr(report, "trade_plan")
        assert hasattr(report, "signal_gate")
