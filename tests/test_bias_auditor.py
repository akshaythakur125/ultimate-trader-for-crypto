import pytest
from datetime import datetime
from ultimate_trader.directional_diagnostics.bias_auditor import BiasAuditor, DirectionalBiasAudit


class TestBiasAuditor:
    def test_summary_all_long_winners(self):
        auditor = BiasAuditor()
        for i in range(10):
            auditor.audit_trade(
                trade_id=f"L{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1),
                direction_taken="LONG", net_r=2.0,
            )
        summary = auditor.summarize()
        assert summary.direction_accuracy == 1.0
        assert summary.long_win_rate == 1.0
        assert summary.short_win_rate == 0.0
        assert summary.total_trades == 10

    def test_summary_all_short_winners(self):
        auditor = BiasAuditor()
        for i in range(5):
            auditor.audit_trade(
                trade_id=f"S{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1),
                direction_taken="SHORT", net_r=1.5,
            )
        summary = auditor.summarize()
        assert summary.direction_accuracy == 1.0
        assert summary.short_win_rate == 1.0
        assert summary.long_win_rate == 0.0

    def test_summary_mixed_directions(self):
        auditor = BiasAuditor()
        for i in range(8):
            auditor.audit_trade(trade_id=f"L{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1), direction_taken="LONG", net_r=2.0 if i < 4 else -1.0)
            auditor.audit_trade(trade_id=f"S{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1), direction_taken="SHORT", net_r=1.5 if i < 2 else -1.0)
        summary = auditor.summarize()
        assert summary.total_trades == 16
        assert summary.long_win_rate == 0.5
        assert summary.short_win_rate == 0.25
        assert summary.long_expectancy > 0
        assert summary.short_expectancy < 0

    def test_summary_empty(self):
        auditor = BiasAuditor()
        summary = auditor.summarize()
        assert summary.total_trades == 0
        assert summary.direction_accuracy == 0.0

    def test_wrong_direction_rate_all_wrong(self):
        auditor = BiasAuditor()
        for i in range(3):
            auditor.audit_trade(
                trade_id=f"T{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1),
                direction_taken="LONG", net_r=-2.0, mfe_r=3.0, mae_r=4.0,
            )
        summary = auditor.summarize()
        assert summary.wrong_direction_rate > 0

    def test_suspected_bias_failure_flag(self):
        auditor = BiasAuditor()
        for i in range(10):
            auditor.audit_trade(
                trade_id=f"T{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1),
                direction_taken="LONG", net_r=-1.0 if i < 6 else 0.5,
                mfe_r=2.0 if i < 6 else 0, mae_r=3.0 if i < 6 else 0,
            )
        summary = auditor.summarize()
        assert summary.suspected_bias_failure

    def test_expectancy_calculation(self):
        auditor = BiasAuditor()
        for i in range(5):
            auditor.audit_trade(trade_id=f"W{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1), direction_taken="LONG", net_r=2.0)
        for i in range(5):
            auditor.audit_trade(trade_id=f"L{i}", symbol="BTCUSDT", signal_time=datetime(2025, 1, 1), direction_taken="LONG", net_r=-1.0)
        summary = auditor.summarize()
        assert abs(summary.long_expectancy - 0.5) < 0.01
