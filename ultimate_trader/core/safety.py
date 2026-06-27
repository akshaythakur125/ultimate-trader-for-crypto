from ultimate_trader.config.settings import Settings
from ultimate_trader.core.errors import LiveTradingDisabledError


def assert_live_trading_allowed(settings: Settings) -> bool:
    if settings.LIVE_TRADING_ENABLED:
        return True
    raise LiveTradingDisabledError(
        "Live trading is disabled. "
        "Set LIVE_TRADING_ENABLED=true and confirm all safety checks to enable."
    )


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]
