import pytest
from datetime import datetime
from ultimate_trader.directional_diagnostics import (
    BiasAuditor,
    DirectionalBiasAudit,
    BiasAuditSummary,
    BiasComponentAttribution,
    ComponentAttributionResult,
    InverseSignalTester,
    InverseSignalResult,
    DirectionConflictDetector,
    DirectionConflictResult,
    TradeFrequencyController,
    TradeFrequencyResult,
    DirectionalReplayReport,
)
from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics, TradeDirection, ExitReason


def make_trade(tid: str, direction: str, net_r: float, comps: dict = None) -> TradeDiagnostics:
    td = TradeDiagnostics(
        trade_id=tid, symbol="BTCUSDT", direction=TradeDirection(direction),
        signal_time=datetime(2025, 1, 1), entry_price=100.0,
        stop_loss=95.0, target_price=110.0,
        exit_price=110.0 if net_r > 0 else 95.0,
        net_r=net_r, gross_r=net_r,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
        directional_components=comps or {},
    )
    return td


class TestDirectionalDiagnostics:
    def test_bias_auditor_summary(self):
        auditor = BiasAuditor()
        auditor.audit_trade(trade_id="T1", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1), direction_taken="LONG", net_r=2.0)
        auditor.audit_trade(trade_id="T2", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1), direction_taken="LONG", net_r=-1.0)
        summary = auditor.summarize()
        assert summary.total_trades == 2
        assert summary.long_win_rate == 0.5

    def test_bias_auditor_via_diagnostics(self):
        auditor = BiasAuditor()
        auditor.audit_trade_diagnostics(make_trade("T1", "LONG", 2.0, {"sweep_bias": 1.0}))
        summary = auditor.summarize()
        assert summary.total_trades == 1

    def test_component_attribution(self):
        attributor = BiasComponentAttribution()
        trades = [
            {"directional_components": {"sweep": 1.0}, "net_r": 2.0, "direction": "LONG", "is_winner": True},
            {"directional_components": {"sweep": -1.0}, "net_r": -1.0, "direction": "SHORT", "is_winner": False},
        ]
        result = attributor.analyze(trades)
        assert len(result.components_helping_direction) > 0 or len(result.components_hurting_direction) > 0

    def test_inverse_signal_tester(self):
        tester = InverseSignalTester()
        trades = [
            {"direction": "LONG", "net_r": 2.0, "confidence": 80.0},
            {"direction": "SHORT", "net_r": -1.0, "confidence": 70.0},
        ]
        result = tester.test_variants_simple(trades)
        assert result.original_trades == 2

    def test_direction_conflict_detector(self):
        detector = DirectionConflictDetector()
        result = detector.detect(lsm_bias="LONG", microstructure_bias="SHORT", orderflow_bias="LONG", strategy_bias="SHORT")
        assert result.has_conflict
        assert result.recommended_action == "BLOCK"

    def test_trade_frequency_controller(self):
        ctrl = TradeFrequencyController(hard_max_candidates_per_day=1)
        now = datetime(2025, 1, 1)
        ctrl.record_trade("BTCUSDT", "LONG", now)
        result = ctrl.check("BTCUSDT", "SHORT", now)
        assert not result.allowed

    def test_directional_replay_report(self):
        orig = {"total_trades": 100, "win_rate": 25.0, "expectancy": -0.5, "profit_factor": 0.8, "avg_trades_per_day": 10.0}
        inv = {"total_trades": 100, "win_rate": 30.0, "expectancy": -0.3, "profit_factor": 0.9, "avg_trades_per_day": 10.0}
        weak = {"total_trades": 40, "win_rate": 35.0, "expectancy": -0.2, "profit_factor": 1.1, "avg_trades_per_day": 4.0}
        attr = ComponentAttributionResult()
        attr.components_helping_direction = ["sweep"]
        attr.components_hurting_direction = ["structure"]
        attr.recommended_reweighting = "Increase sweep weight"
        bias = BiasAuditSummary()
        bias.total_trades = 100
        bias.long_win_rate = 24.0
        bias.short_win_rate = 26.0
        bias.direction_accuracy = 0.25
        bias.wrong_direction_rate = 0.75
        bias.audit_summary = "BIAS FAILURE SUSPECTED — high wrong-direction rate"
        report = DirectionalReplayReport.generate(orig, inv, weak, attr, bias)
        assert "DIRECTIONAL" in report
        assert "RECOMMENDATION" in report
