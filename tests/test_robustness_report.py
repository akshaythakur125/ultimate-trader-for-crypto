import pytest
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.robustness_lab.robustness_report import RobustnessReport
from ultimate_trader.robustness_lab.edge_stability import EdgeClassification


class TestRobustnessReport:
    def test_generate_no_data(self):
        report = RobustnessReport.generate(FrozenConfig(), [], [], [], [], EdgeClassification())
        assert "ROBUSTNESS VALIDATION REPORT" in report
        assert "NONE" in report
        assert "Frozen Config" in report

    def test_generate_with_data(self):
        ec = EdgeClassification(verdict="NO_EDGE", reason="test", total_out_of_sample_trades=10)
        report = RobustnessReport.generate(FrozenConfig(), [], [], [], [], ec)
        assert "NO_EDGE" in report

    def test_config_summary_in_report(self):
        report = RobustnessReport.generate(FrozenConfig(), [], [], [], [], EdgeClassification())
        assert "Frozen Selectivity Config" in report
