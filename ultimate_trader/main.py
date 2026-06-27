import sys
import uuid

from ultimate_trader.config.settings import Settings
from ultimate_trader.core.constants import HypothesisStatus
from ultimate_trader.core.health import run_health_checks
from ultimate_trader.core.logger import setup_logger
from ultimate_trader.core.errors import LiveTradingDisabledError
from ultimate_trader.core.safety import assert_live_trading_allowed, mask_secret
from ultimate_trader.market_brain.knowledge_base import MarketKnowledgeBase
from ultimate_trader.schemas.hypothesis import TradingHypothesis
from ultimate_trader.storage.database import init_database

logger = setup_logger()


def create_sample_hypothesis() -> TradingHypothesis:
    return TradingHypothesis(
        hypothesis_id=f"HYP-{uuid.uuid4().hex[:8].upper()}",
        name="Sample Observation Hypothesis",
        description=(
            "A schema-validation-only hypothesis. No real strategy or trading logic. "
            "This exists solely to prove the hypothesis data model works."
        ),
        edge_theory="Placeholder — no edge claimed.",
        expected_market_regime="trending",
        required_liquidity_condition="liquidity_sweep_detected",
        required_orderflow_condition="aggressive_buying_confirmed",
        expected_holding_time_hours=6.0,
        minimum_rr=3.0,
        preferred_rr=5.0,
        entry_logic_description="Not implemented — schema validation only.",
        invalidation_logic_description="Not implemented — schema validation only.",
        expected_failure_conditions="Not implemented — schema validation only.",
        status=HypothesisStatus.DRAFT,
    )


def main() -> None:
    settings = Settings()

    logger.info(f"Initializing {settings.APP_NAME}...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Log level: {settings.LOG_LEVEL}")

    _, session_factory = init_database(settings.DATABASE_URL)
    logger.info("Database ready")

    health = run_health_checks(settings)
    if health.healthy:
        logger.info("Health check passed")
    else:
        failed = [k for k, v in health.checks.items() if not v]
        logger.warning(f"Health check warnings: {failed}")

    if settings.PAPER_TRADING_MODE:
        logger.info("Paper trading mode active")

    if not settings.LIVE_TRADING_ENABLED:
        logger.info("Live trading disabled")

    try:
        assert_live_trading_allowed(settings)
    except LiveTradingDisabledError:
        logger.info("Safety checks passed")

    if settings.BINGX_API_KEY:
        logger.info(f"BingX API key configured: {mask_secret(settings.BINGX_API_KEY)}")
    if settings.BINGX_SECRET_KEY:
        logger.info(f"BingX secret key configured: {mask_secret(settings.BINGX_SECRET_KEY)}")

    knowledge_base = MarketKnowledgeBase()
    kb_health = knowledge_base.health_check()
    if all(kb_health.values()):
        logger.info(
            f"Market Knowledge Framework loaded — "
            f"{knowledge_base.principle_count} principles across "
            f"{len(kb_health)} categories"
        )
    else:
        failed_kb = [k for k, v in kb_health.items() if not v]
        logger.warning(f"Knowledge base health warnings: {failed_kb}")

    hypothesis = create_sample_hypothesis()
    logger.info(
        f"Sample hypothesis created: {hypothesis.hypothesis_id} "
        f"({hypothesis.name}) — status: {hypothesis.status.value}"
    )

    logger.info("Ultimate Trader initialized successfully")
    logger.info("Intelligence foundation ready")


if __name__ == "__main__":
    main()
