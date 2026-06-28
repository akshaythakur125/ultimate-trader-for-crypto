from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab import FrozenConfig
from ultimate_trader.data_engine import DatasetRegistry
from ultimate_trader.drawdown_control import RiskGovernorConfig


class TestLongHistoryRobustness:
    def test_frozen_config_unchanged(self):
        cfg = FrozenConfig()
        assert cfg.rank_grade_a_plus_min == 85.0
        assert cfg.min_rr == 3.0
        assert cfg.allowed_grades == ("A_PLUS", "A")
        assert cfg.strategy_confidence_threshold == 60.0
        assert cfg.min_confluence_score == 50.0
        assert cfg.min_directional_confidence == 0.55

    def test_frozen_config_does_not_change(self):
        cfg = FrozenConfig()
        keys = ["rank_grade_a_plus_min", "min_confluence_score", "min_rr",
                "hard_max_per_day", "max_losses_per_day", "strategy_confidence_threshold"]
        for k in keys:
            original = getattr(cfg, k)
            with_second = getattr(FrozenConfig(), k)
            assert original == with_second, f"{k} changed between instances"

    def test_risk_governor_consec_unchanged(self):
        cfg = RiskGovernorConfig()
        assert cfg.max_consecutive_losses_per_day == 2

    def test_risk_governor_other_rules(self):
        cfg = RiskGovernorConfig()
        assert cfg.max_daily_loss_r == 3.0
        assert cfg.max_weekly_loss_r == 6.0
        assert cfg.max_total_consecutive_losses == 5
        assert cfg.defensive_drawdown_threshold == 8.0
        assert cfg.capital_preservation_drawdown_threshold == 12.0

    def test_dataset_registry_quality_enum(self):
        from ultimate_trader.data_engine.dataset_registry import QualityStatus
        assert "GOOD" in QualityStatus.__members__
        assert "BAD" in QualityStatus.__members__
        assert "TOO_SHORT" in QualityStatus.__members__
        assert "ACCEPTABLE_WITH_GAPS" in QualityStatus.__members__

    def test_compute_metrics_exists(self):
        from ultimate_trader.robustness_lab import compute_metrics
        from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection
        from datetime import datetime
        trades = [
            ReplayTrade(trade_id="T1", symbol="BTCUSDT",
                        direction=TradeDirection.LONG,
                        signal_time=datetime(2026, 1, 1), net_r=1.0),
            ReplayTrade(trade_id="T2", symbol="BTCUSDT",
                        direction=TradeDirection.SHORT,
                        signal_time=datetime(2026, 1, 1), net_r=-0.5),
        ]
        m = compute_metrics(trades)
        assert m["total_trades"] == 2
        assert m["win_rate"] == 0.5
        assert m["expectancy"] == 0.25
        assert m["profit_factor"] == 2.0

    def test_frozen_config_summary_contains_config(self):
        from ultimate_trader.robustness_lab.frozen_config import config_summary
        cfg = FrozenConfig()
        summary = config_summary(cfg)
        assert "Frozen Selectivity Config" in summary
        assert "85.0" in summary
        assert "3.0" in summary

    def test_dataset_registry_creates_entry(self):
        reg = DatasetRegistry()
        assert len(reg.datasets) == 0
        assert reg.get("BTCUSDT", "15m") is None
