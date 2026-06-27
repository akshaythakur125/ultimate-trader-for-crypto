import sys
import uuid

from ultimate_trader.config.settings import Settings
from ultimate_trader.core.constants import HypothesisStatus
from ultimate_trader.core.health import run_health_checks
from ultimate_trader.core.logger import setup_logger
from ultimate_trader.core.errors import LiveTradingDisabledError
from ultimate_trader.core.safety import assert_live_trading_allowed, mask_secret
from ultimate_trader.cognitive_engine.observation import Observation, ObservationType
from ultimate_trader.cognitive_engine.reasoning_chain import Reasoner
from ultimate_trader.market_brain.knowledge_base import MarketKnowledgeBase
from ultimate_trader.memory_engine.case_library import CaseLibrary
from ultimate_trader.memory_engine.confidence_calibrator import ConfidenceCalibrator
from ultimate_trader.memory_engine.pattern_signature import PatternSignature
from ultimate_trader.memory_engine.similarity_engine import SimilarityEngine
from ultimate_trader.belief_engine.bayesian_updater import BayesianUpdater
from ultimate_trader.belief_engine.expected_value import ExpectedValueCalculator
from ultimate_trader.belief_engine.probability_calibrator import ProbabilityCalibrator
from ultimate_trader.belief_engine.scenario_probability import ScenarioProbabilityEngine
from ultimate_trader.belief_engine.decision_thresholds import DecisionThresholds
from ultimate_trader.belief_engine.risk_adjusted_utility import RiskAdjustedUtilityEngine
from ultimate_trader.metacognition_engine.metacognitive_report import (
    MetacognitiveReportGenerator,
)
from ultimate_trader.schemas.hypothesis import TradingHypothesis
from ultimate_trader.storage.database import init_database
from ultimate_trader.event_bus import (
    EventBus,
    EventStore,
    EventType,
    get_default_bus,
    get_default_store,
)
from ultimate_trader.validation_lab import (
    DatasetSplitter,
    WalkForwardValidator,
    MonteCarloSimulator,
    ValidationGate,
)

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

    reasoner = Reasoner(kb=knowledge_base)
    chain = reasoner.reason([
        Observation(
            observation_id="OBS-HEALTH-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Health check observation — no strategy involved.",
            source="system_health",
        ),
    ])
    logger.info(
        f"Cognitive Reasoning Engine loaded — "
        f"chain {chain.chain_id}: bias={chain.preliminary_bias}, "
        f"confidence={chain.confidence_after:.0f}/100"
    )

    metacognitive_report_gen = MetacognitiveReportGenerator()
    report = metacognitive_report_gen.generate(chain)
    audit_passed = report.decision_audit.audit_passed if report.decision_audit else False
    bias_count = len(report.bias_detection.detected_biases) if report.bias_detection else 0
    readiness_score = report.trade_readiness.readiness_score if report.trade_readiness else 0.0
    logger.info(
        f"Meta-Cognition Engine loaded — "
        f"audit_passed={audit_passed}, "
        f"biases={bias_count}, "
        f"readiness_score={readiness_score:.0f}/100, "
        f"final_action={report.final_action}"
    )

    case_library = CaseLibrary()
    similarity_engine = SimilarityEngine()
    calibrator = ConfidenceCalibrator()

    health_sig = PatternSignature(
        signature_id="SIG-HEALTH-001",
        symbol="BTCUSDT",
        timeframe="1h",
        regime_label="trending",
        liquidity_state="normal",
        orderflow_state="neutral",
        volatility_state="normal",
        trend_state="bullish",
    )
    memory_ok = case_library.count() == 0
    sim_ok = similarity_engine.compute_similarity(health_sig, health_sig) > 99.0
    cal_ok = calibrator.calibrate(50.0, health_sig, []).insufficient_memory is True
    logger.info(
        f"Market Memory Engine loaded — "
        f"case_library={case_library.count()} cases, "
        f"similarity_ok={sim_ok}, "
        f"calibrator_ok={cal_ok}"
    )

    bayesian_updater = BayesianUpdater()
    posterior = bayesian_updater.update(prior=0.5, likelihood_if_true=0.8, likelihood_if_false=0.2)
    bayes_ok = posterior > 0.5

    scenario_engine = ScenarioProbabilityEngine()
    belief_state = scenario_engine.initialize_default_beliefs("BTCUSDT", "1h")
    scenario_ok = belief_state.dominant_belief is not None

    ev_calc = ExpectedValueCalculator()
    ev_result = ev_calc.calculate(0.6, 3.0, 0.4, 1.0)
    ev_ok = ev_result.is_positive_ev

    utility_engine = RiskAdjustedUtilityEngine()
    util_result = utility_engine.calculate(raw_expected_value_r=1.0)
    util_ok = util_result.utility_grade.value in ("GOOD", "EXCELLENT", "MARGINAL")

    prob_calibrator = ProbabilityCalibrator()
    calib_result = prob_calibrator.calibrate(raw_probability=0.8, similar_cases_count=3)
    calib_ok = calib_result.sufficient_sample_size is False

    thresholds = DecisionThresholds()
    thresh_result = thresholds.evaluate(
        expected_value_r=1.0, utility_grade="GOOD", no_trade_probability=0.1,
        uncertainty_score=40.0, estimated_win_probability=0.6, required_win_rate=0.33,
    )
    thresh_ok = thresh_result.mathematically_acceptable is True

    logger.info(
        f"Bayesian Belief Engine loaded — "
        f"bayes_ok={bayes_ok}, "
        f"scenarios_ok={scenario_ok}, "
        f"ev_ok={ev_ok}, "
        f"utility_ok={util_ok}, "
        f"calibrator_ok={calib_ok}, "
        f"thresholds_ok={thresh_ok}"
    )

    event_bus = get_default_bus()
    event_store = get_default_store()
    bus_ok = isinstance(event_bus, EventBus)
    store_ok = isinstance(event_store, EventStore)
    bus_events = [et.value for et in EventType]
    logger.info(
        f"Event Bus loaded — "
        f"bus_ok={bus_ok}, "
        f"store_ok={store_ok}, "
        f"event_types={len(bus_events)}"
    )

    splitter = DatasetSplitter()
    wf_validator = WalkForwardValidator()
    mc_simulator = MonteCarloSimulator()
    gate = ValidationGate()

    from datetime import datetime, timedelta
    split = splitter.split(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 1, 1),
    )
    split_ok = splitter.validate_no_overlap(split)
    wf_ok = not wf_validator.evaluate([[], []]).passed
    mc_ok = not mc_simulator.simulate([]).passed
    gate_ok = not gate.evaluate(
        metrics=type("_", (), {"total_trades": 0, "expectancy_r": 0, "profit_factor": 0,
                               "max_daily_drawdown_percent": 0})(),
        walk_forward_result=type("_", (), {"passed": False})(),
        out_of_sample_result=type("_", (), {"passed": False})(),
        monte_carlo_result=type("_", (), {"passed": False, "probability_of_ruin": 0})(),
        sensitivity_result=type("_", (), {"passed": False, "scenarios_tested": 0,
                                          "scenarios_passed": 0})(),
    ).passed

    hypothesis = create_sample_hypothesis()
    logger.info(
        f"Sample hypothesis created: {hypothesis.hypothesis_id} "
        f"({hypothesis.name}) — status: {hypothesis.status.value}"
    )

    logger.info(
        f"Scientific Validation Engine loaded — "
        f"splitter_ok={split_ok}, "
        f"walk_forward_ok={wf_ok}, "
        f"monte_carlo_ok={mc_ok}, "
        f"validation_gate_ok={gate_ok}"
    )

    logger.info("Ultimate Trader initialized successfully")
    logger.info("Intelligence foundation ready")


if __name__ == "__main__":
    main()
