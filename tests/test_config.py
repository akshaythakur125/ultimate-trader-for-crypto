"""Tests for configuration loading and defaults."""

import os
from unittest.mock import patch

from ultimate_trader.config.settings import Settings


class TestConfigDefaults:
    def test_settings_load_with_defaults(self):
        settings = Settings()
        assert settings.APP_NAME == "Ultimate Trader"
        assert settings.ENVIRONMENT == "development"
        assert settings.LOG_LEVEL == "INFO"
        assert settings.DATABASE_URL == "sqlite:///ultimate_trader.db"

    def test_live_trading_disabled_by_default(self):
        settings = Settings()
        assert settings.LIVE_TRADING_ENABLED is False

    def test_paper_trading_enabled_by_default(self):
        settings = Settings()
        assert settings.PAPER_TRADING_MODE is True

    def test_target_opportunities_defaults(self):
        settings = Settings()
        assert settings.TARGET_MIN_PROFITABLE_OPPORTUNITIES_PER_DAY == 2
        assert settings.TARGET_MAX_PROFITABLE_OPPORTUNITIES_PER_DAY == 4

    def test_risk_defaults(self):
        settings = Settings()
        assert settings.MAX_DAILY_DRAWDOWN_PERCENT == 10.0
        assert settings.MIN_ACCEPTABLE_WIN_RATE == 0.60
        assert settings.MIN_ACCEPTABLE_RR == 3.0
        assert settings.PREFERRED_RR == 5.0

    def test_confidence_and_risk_scores_defaults(self):
        settings = Settings()
        assert settings.MIN_CONFIDENCE_SCORE == 70.0
        assert settings.MAX_RISK_SCORE == 40.0

    def test_holding_time_defaults(self):
        settings = Settings()
        assert settings.DEFAULT_HOLDING_TIME_MIN_HOURS == 4.0
        assert settings.DEFAULT_HOLDING_TIME_MAX_HOURS == 8.0

    def test_env_override(self):
        with patch.dict(os.environ, {"APP_NAME": "Test Trader", "ENVIRONMENT": "staging"}):
            settings = Settings()
            assert settings.APP_NAME == "Test Trader"
            assert settings.ENVIRONMENT == "staging"
