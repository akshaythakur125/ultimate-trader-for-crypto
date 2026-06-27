"""Tests to ensure live trading is disabled by default and safety blocks execution."""

import pytest

from ultimate_trader.config.settings import Settings
from ultimate_trader.core.errors import LiveTradingDisabledError
from ultimate_trader.core.safety import assert_live_trading_allowed


class TestLiveTradingDisabled:
    def test_live_trading_disabled_by_default(self):
        settings = Settings()
        assert settings.LIVE_TRADING_ENABLED is False

    def test_assert_live_trading_raises_by_default(self):
        settings = Settings()
        with pytest.raises(LiveTradingDisabledError) as exc_info:
            assert_live_trading_allowed(settings)
        assert "Live trading is disabled" in str(exc_info.value)

    def test_live_trading_enabled_does_not_raise(self):
        settings = Settings(LIVE_TRADING_ENABLED=True)
        try:
            result = assert_live_trading_allowed(settings)
            assert result is True
        except LiveTradingDisabledError:
            pytest.fail("assert_live_trading_allowed raised unexpectedly")

    def test_paper_trading_mode_active_by_default(self):
        settings = Settings()
        assert settings.PAPER_TRADING_MODE is True

    def test_no_api_keys_exposed_in_logging(self):
        settings = Settings(
            BINGX_API_KEY="sk-test-secret-key-12345",
            BINGX_SECRET_KEY="secret-value-abc",
            LIVE_TRADING_ENABLED=True,
        )
        log_line = f"API Key: {settings.BINGX_API_KEY[:4]}...{settings.BINGX_API_KEY[-4:]}"
        assert "sk-test-secret-key-12345" not in log_line
        assert "sk-t" in log_line
        assert "12345" not in log_line.split("...")[1]
