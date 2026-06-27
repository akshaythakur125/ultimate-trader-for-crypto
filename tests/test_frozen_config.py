import pytest
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig, freeze_current_config, config_summary


class TestFrozenConfig:
    def test_config_is_frozen(self):
        cfg = FrozenConfig()
        with pytest.raises(Exception):
            cfg.min_confluence_score = 99.0

    def test_config_has_all_fields(self):
        cfg = FrozenConfig()
        assert cfg.min_confluence_score == 50.0
        assert cfg.min_directional_confidence == 0.55
        assert cfg.max_conflict_score == 0.4
        assert cfg.max_reversal_risk_score == 50.0
        assert cfg.max_risk_score == 40.0
        assert cfg.min_rr == 3.0
        assert cfg.allowed_grades == ("A_PLUS", "A")
        assert cfg.hard_max_per_day == 4
        assert cfg.strategy_confidence_threshold == 60.0

    def test_freeze_current_config(self):
        cfg = freeze_current_config()
        assert isinstance(cfg, FrozenConfig)

    def test_config_summary(self):
        cfg = FrozenConfig()
        summary = config_summary(cfg)
        assert "Frozen Selectivity Config" in summary
        assert "Min confluence" in summary
        assert "Hard max/day" in summary

    def test_config_rank_grades(self):
        cfg = FrozenConfig()
        assert cfg.rank_grade_a_plus_min == 85.0
        assert cfg.rank_grade_a_min == 70.0

    def test_config_cooldowns(self):
        cfg = FrozenConfig()
        assert cfg.same_symbol_cooldown_minutes == 120
        assert cfg.same_direction_cooldown_minutes == 180

    def test_config_loss_threshold(self):
        cfg = FrozenConfig()
        assert cfg.loss_threshold_increase == 0.10
        assert cfg.max_losses_per_day == 2

    def test_config_weights_tuple(self):
        cfg = FrozenConfig()
        assert len(cfg.rank_score_weights) == 11
        names = [w[0] for w in cfg.rank_score_weights]
        assert "confluence" in names
        assert "stop_quality" in names
