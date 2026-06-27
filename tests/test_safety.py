"""Tests for safety module — live trading blocking and secret masking."""

import pytest

from ultimate_trader.config.settings import Settings
from ultimate_trader.core.errors import LiveTradingDisabledError
from ultimate_trader.core.safety import assert_live_trading_allowed, mask_secret


class TestSafety:
    def test_live_trading_blocked_by_default(self):
        settings = Settings()
        with pytest.raises(LiveTradingDisabledError):
            assert_live_trading_allowed(settings)

    def test_mask_secret_full(self):
        assert mask_secret("") == ""
        assert mask_secret("abc") == "***"
        assert mask_secret("abcdefgh") == "********"

    def test_mask_secret_partial(self):
        masked = mask_secret("sk-test1234567890key")
        assert masked.startswith("sk-t")
        assert masked.endswith("key")
        assert "*" in masked
        assert "1234567890" not in masked

    def test_mask_secret_short(self):
        assert mask_secret("12345678") == "********"
        assert mask_secret("1234567") == "*******"

    def test_live_trading_allowed_when_enabled(self):
        settings = Settings(LIVE_TRADING_ENABLED=True)
        result = assert_live_trading_allowed(settings)
        assert result is True
