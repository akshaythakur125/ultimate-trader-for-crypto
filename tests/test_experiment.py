import pytest

from ultimate_trader.validation_lab.experiment import (
    ExperimentStatus,
    TradingExperiment,
)


class TestTradingExperiment:
    def test_default_status_is_draft(self):
        exp = TradingExperiment(
            experiment_id="EXP-001",
            hypothesis_id="RH-001",
        )
        assert exp.status == ExperimentStatus.DRAFT

    def test_experiment_with_all_fields(self):
        exp = TradingExperiment(
            experiment_id="EXP-002",
            hypothesis_id="RH-002",
            hypothesis_name="Breakout Test",
            experiment_name="Validation Run 1",
            symbol_universe=["BTCUSDT"],
            timeframe="1h",
        )
        assert exp.hypothesis_name == "Breakout Test"
        assert "BTCUSDT" in exp.symbol_universe
