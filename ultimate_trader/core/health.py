from dataclasses import dataclass, field
from datetime import datetime, timezone

from ultimate_trader.config.settings import Settings


@dataclass
class HealthStatus:
    healthy: bool
    checks: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def run_health_checks(settings: Settings) -> HealthStatus:
    checks: dict[str, bool] = {
        "environment": settings.ENVIRONMENT in ("development", "staging", "production"),
        "database_url": bool(settings.DATABASE_URL),
        "paper_trading": settings.PAPER_TRADING_MODE,
        "live_trading_disabled_by_default": not settings.LIVE_TRADING_ENABLED,
        "app_name_configured": bool(settings.APP_NAME),
        "min_win_rate_configured": settings.MIN_ACCEPTABLE_WIN_RATE > 0,
        "min_rr_configured": settings.MIN_ACCEPTABLE_RR > 0,
        "max_drawdown_configured": settings.MAX_DAILY_DRAWDOWN_PERCENT > 0,
    }

    all_healthy = all(checks.values())
    return HealthStatus(healthy=all_healthy, checks=checks)
