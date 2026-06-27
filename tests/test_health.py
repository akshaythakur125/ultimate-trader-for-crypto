"""Tests for health check module."""

from ultimate_trader.config.settings import Settings
from ultimate_trader.core.health import run_health_checks


class TestHealth:
    def test_health_check_passes_with_defaults(self):
        settings = Settings()
        health = run_health_checks(settings)
        assert health.healthy is True

    def test_health_check_contains_all_expected_checks(self):
        settings = Settings()
        health = run_health_checks(settings)
        expected_keys = [
            "environment",
            "database_url",
            "paper_trading",
            "live_trading_disabled_by_default",
            "app_name_configured",
            "min_win_rate_configured",
            "min_rr_configured",
            "max_drawdown_configured",
        ]
        for key in expected_keys:
            assert key in health.checks, f"Missing health check: {key}"

    def test_health_check_timestamp(self):
        settings = Settings()
        health = run_health_checks(settings)
        assert health.timestamp is not None

    def test_health_check_fails_on_bad_environment(self):
        settings = Settings(ENVIRONMENT="invalid")
        health = run_health_checks(settings)
        assert health.checks["environment"] is False
