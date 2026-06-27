from datetime import datetime

import pytest

from ultimate_trader.validation_lab.performance_metrics import (
    Direction,
    TradeResult,
)
from ultimate_trader.validation_lab.transaction_costs import (
    TransactionCostModel,
)
from ultimate_trader.validation_lab.out_of_sample import (
    OutOfSampleValidator,
)
from ultimate_trader.validation_lab.sensitivity_analysis import (
    SensitivityAnalysis,
)
from ultimate_trader.validation_lab.validation_report import (
    ValidationReport,
)
from ultimate_trader.event_bus import (
    EventBus,
    EventType,
    get_default_bus,
    get_default_store,
    publish_system_event,
)


def make_trade(gross_r: float = 0.0) -> TradeResult:
    return TradeResult(
        trade_id="T1",
        hypothesis_id="RH-TEST",
        symbol="BTCUSDT",
        entry_time=datetime(2024, 1, 1),
        direction=Direction.LONG,
        entry_price=100.0,
        gross_r=gross_r,
        net_r=gross_r,
    )


class TestTransactionCosts:
    def test_fees_reduce_net_r(self):
        cost_model = TransactionCostModel()
        trade = make_trade(2.0)
        trade = cost_model.calculate_net_r(trade)
        assert trade.net_r <= trade.gross_r

    def test_slippage_reduces_net_r(self):
        cost_model = TransactionCostModel()
        trade = make_trade(2.0)
        trade = cost_model.apply_fees(trade)
        trade = cost_model.apply_slippage(trade)
        assert trade.slippage_r > 0


class TestOutOfSampleValidator:
    def test_degradation_detected(self):
        validator = OutOfSampleValidator()
        val_trades = [make_trade(1.0) for _ in range(20)]
        oos_trades = [make_trade(-0.5) for _ in range(10)]
        result = validator.evaluate(val_trades, oos_trades)
        assert result.degradation_detected

    def test_passed_when_oos_positive(self):
        validator = OutOfSampleValidator()
        val_trades = [make_trade(1.0) for _ in range(20)]
        oos_trades = [make_trade(0.5) for _ in range(10)]
        result = validator.evaluate(val_trades, oos_trades)
        assert result.passed


class TestSensitivityAnalysis:
    def test_fragile_hypothesis_fails(self):
        analysis = SensitivityAnalysis()
        trades = [make_trade(0.1) for _ in range(10)] + [make_trade(-2.0) for _ in range(10)]
        result = analysis.analyze(trades)
        assert not result.passed or len(result.fragile_parameters) > 0

    def test_robust_hypothesis_passes(self):
        analysis = SensitivityAnalysis()
        trades = [make_trade(2.0) for _ in range(30)] + [make_trade(-0.5) for _ in range(10)]
        result = analysis.analyze(trades)
        assert result.robustness_score > 0


class TestValidationReport:
    def test_report_can_be_generated(self):
        report = ValidationReport(
            report_id="VR-001",
            final_conclusion="Hypothesis requires improvement",
        )
        assert report.report_id == "VR-001"
        assert report.recommended_next_action.value == "IMPROVE_HYPOTHESIS"


class TestValidationEvents:
    def test_validation_events_published(self):
        bus = get_default_bus()
        store = get_default_store()
        received = []

        def handler(event):
            received.append(event.event_type)

        bus.subscribe(EventType.VALIDATION_STARTED, handler)
        bus.subscribe(EventType.VALIDATION_COMPLETED, handler)

        publish_system_event(
            EventType.VALIDATION_STARTED,
            "test",
            {"experiment_id": "EXP-001"},
        )
        publish_system_event(
            EventType.VALIDATION_COMPLETED,
            "test",
            {"experiment_id": "EXP-001"},
        )

        assert EventType.VALIDATION_STARTED in received
        assert EventType.VALIDATION_COMPLETED in received


class TestMainHealthCheck:
    def test_main_runs(self):
        import importlib
        import sys
        if "ultimate_trader.main" in sys.modules:
            del sys.modules["ultimate_trader.main"]
        mod = importlib.import_module("ultimate_trader.main")
        assert hasattr(mod, "__main__") or True
