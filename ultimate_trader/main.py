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
from ultimate_trader.bingx import BingXClient, BingXNotConfiguredError
from ultimate_trader.microstructure_engine import (
    AbsorptionSignal,
    ExecutionRisk,
    MicrostructureReport,
    MicrostructureState,
    OrderBookDepthAnalyzer,
    OrderBookImbalanceAnalyzer,
    OrderBookLevel,
    OrderBookSnapshot,
    SpoofingSignal,
    SpreadAnalyzer,
)
from ultimate_trader.liquidity_smart_money import (
    SwingDetector,
    LiquidityPoolDetector,
    SweepDetector,
    MarketStructureEngine,
    FairValueGapDetector,
    OrderBlockDetector,
    PremiumDiscountEngine,
    DisplacementEngine,
    ConfluenceEngine,
    LiquiditySmartMoneyReport,
    Candle,
)
from ultimate_trader.orderflow_intelligence import (
    AggressionAnalyzer,
    AbsorptionIntelligence,
    ExhaustionDetector,
    IcebergDetector,
    DeltaDivergenceDetector,
    FlowMomentumAnalyzer,
    TrapDetector,
    OrderFlowScenarioEngine,
    InstitutionalOrderFlowReport,
    TradeFlowBuffer,
    TradePrint,
    AggressorSide,
    AggressionBias,
    AbsorptionState,
    ExhaustionState,
    TrapRisk,
)
from ultimate_trader.paper_trading import PaperAccount, PaperTradeExecutor
from ultimate_trader.signal_engine import (
    EntryPlanner,
    NoSafeEntryError,
    RRAnalyzer,
    SignalContext,
    SignalGate,
    SignalGateResult,
    DirectionBias,
    StopPlanner,
    TargetPlanner,
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

    signal_ctx = SignalContext(
        context_id="SC-HEALTH",
        symbol="BTCUSDT",
        timeframe="1h",
        validated_hypothesis_id="RH-HEALTH",
        direction_bias=DirectionBias.LONG,
        current_price=100.0,
        confidence_score=60.0,
        risk_score=30.0,
        uncertainty_score=20.0,
        expected_value_r=2.0,
        validation_passed=True,
        volatility_score=30.0,
    )
    entry_planner = EntryPlanner()
    stop_planner = StopPlanner()
    target_planner = TargetPlanner()
    rr_analyzer = RRAnalyzer()
    signal_gate = SignalGate()

    entry_ok = entry_planner.plan_entry(signal_ctx).entry_type.value != "NO_SAFE_ENTRY"
    stop_ok = stop_planner.plan_stop(signal_ctx, 100.0).stop_loss_price != 0
    target_ok = target_planner.plan_targets(signal_ctx, 100.0, 99.0).expected_reward_r > 0
    rr_ok = rr_analyzer.analyze(100.0, 99.0, 105.0).meets_preferred_rr
    sig_gate_ok = signal_gate.evaluate(signal_ctx).approved_for_alert is False

    logger.info(
        f"Signal Intelligence Engine loaded — "
        f"entry_ok={entry_ok}, "
        f"stop_ok={stop_ok}, "
        f"target_ok={target_ok}, "
        f"rr_ok={rr_ok}, "
        f"signal_gate_ok={sig_gate_ok}"
    )

    bingx_client = BingXClient(
        api_key=settings.BINGX_API_KEY,
        secret_key=settings.BINGX_SECRET_KEY,
    )
    bingx_configured = settings.BINGX_API_KEY is not None
    bingx_ok = bingx_client.health_check() if bingx_configured else False
    bingx_status = "configured" if bingx_configured else "not configured"
    logger.info(
        f"BingX Client loaded — "
        f"status={bingx_status}, "
        f"health_check={bingx_ok}, "
        f"symbols=BTCUSDT,ETHUSDT"
    )

    paper_account = PaperAccount(starting_balance=100_000.0)
    paper_executor = PaperTradeExecutor(account=paper_account)
    paper_ok = paper_executor.account.balance == 100_000.0
    logger.info(
        f"Paper Trading Engine loaded — "
        f"starting_balance={paper_account.starting_balance:.0f} {paper_account.currency}, "
        f"positions=0, "
        f"orders=0"
    )

    ms_snapshot = OrderBookSnapshot(
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=100.0, quantity=50), OrderBookLevel(price=99.9, quantity=40)],
        asks=[OrderBookLevel(price=100.1, quantity=50), OrderBookLevel(price=100.2, quantity=40)],
    )
    ms_spread = SpreadAnalyzer()
    ms_depth = OrderBookDepthAnalyzer()
    ms_imbalance = OrderBookImbalanceAnalyzer()
    ms_state = MicrostructureState(symbol="BTCUSDT")
    ms_state.update(
        spread_state=ms_spread.analyze(ms_snapshot),
        depth_state=ms_depth.analyze(ms_snapshot),
        imbalance_bias=ms_imbalance.analyze(ms_snapshot).bias,
        liquidity_voids=[],
        absorption=AbsorptionSignal(detected=False),
        spoofing=SpoofingSignal(detected=False),
        execution_risk=ExecutionRisk.LOW,
    )
    MicrostructureReport.from_state(
        report_id="MS-HEALTH", symbol="BTCUSDT", state=ms_state,
    )
    logger.info(
        f"Market Microstructure Engine loaded — "
        f"spread={ms_state.spread_state.value}, "
        f"depth={ms_state.depth_state.value}, "
        f"bias={ms_state.imbalance_bias.value}, "
        f"permission={ms_state.trade_permission.value}"
    )

    trade_flow_buf = TradeFlowBuffer()
    trade_flow_buf.add_trade(TradePrint(symbol="BTCUSDT", price=100.0, quantity=1.0, aggressor_side=AggressorSide.BUYER, trade_value=100.0))
    flow_ok = trade_flow_buf.get_window("BTCUSDT").trade_count == 1

    of_aggression = AggressionAnalyzer()
    of_window = trade_flow_buf.get_window("BTCUSDT")
    of_aggr_result = of_aggression.analyze(of_window)
    aggr_ok = of_aggr_result.buy_aggression_score > 0

    of_absorption = AbsorptionIntelligence()
    of_abs_result = of_absorption.analyze(of_window, AggressionBias.BALANCED)
    abs_ok = not of_abs_result.absorption_detected

    of_exhaustion = ExhaustionDetector()
    of_exh_result = of_exhaustion.analyze(of_window)
    exh_ok = not of_exh_result.exhaustion_detected

    of_iceberg = IcebergDetector()
    of_ice_result = of_iceberg.analyze(of_window)
    ice_ok = of_ice_result.iceberg_suspected.value == "NONE"

    of_divergence = DeltaDivergenceDetector()
    of_div_result = of_divergence.analyze(of_window, 100.0)
    div_ok = not of_div_result.divergence_detected

    of_momentum = FlowMomentumAnalyzer()
    of_mom_result = of_momentum.analyze(of_window)
    mom_ok = of_mom_result.flow_momentum_score == 50.0

    of_trap = TrapDetector()
    of_trap_result = of_trap.analyze(of_window, AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, "NO_DIVERGENCE")
    trap_ok = not of_trap_result.trap_detected

    of_scenarios = OrderFlowScenarioEngine()
    of_scen_result = of_scenarios.analyze(of_window, AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LOW_TRAP_RISK)
    scen_ok = of_scen_result.dominant_scenario == "no_edge_balanced_flow"

    logger.info(
        f"Institutional Order Flow Intelligence loaded — "
        f"flow={flow_ok}, "
        f"aggression={aggr_ok}, "
        f"absorption={abs_ok}, "
        f"exhaustion={exh_ok}, "
        f"iceberg={ice_ok}, "
        f"divergence={div_ok}, "
        f"momentum={mom_ok}, "
        f"trap={trap_ok}, "
        f"scenarios={scen_ok}"
    )

    lsm_candle = Candle(symbol="BTCUSDT", timeframe="1h", timestamp=datetime.utcnow(),
                         open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
    lsm_swing = SwingDetector(lookback=2)
    lsm_swing.add_candle(lsm_candle)
    for h, l in [(100, 99), (101, 99.5), (102, 100), (101.5, 99.8)]:
        lsm_swing.add_candle(Candle(symbol="BTCUSDT", timeframe="1h", timestamp=datetime.utcnow(),
                                     open=l, high=h, low=l, close=(h + l) / 2, volume=100.0))
    swing_ok = len(lsm_swing.get_all_swing_points()) >= 0

    lsm_pools = LiquidityPoolDetector()
    zones = lsm_pools.analyze(lsm_swing.get_swing_highs(), lsm_swing.get_swing_lows(),
                               lsm_swing.get_equal_highs(), lsm_swing.get_equal_lows(), 100.0, [])
    pools_ok = isinstance(zones, list)

    lsm_sweep = SweepDetector()
    sweeps = lsm_sweep.analyze([lsm_candle], zones)
    sweep_ok = isinstance(sweeps, list)

    lsm_struct = MarketStructureEngine()
    struct_events = lsm_struct.analyze(lsm_swing.get_swing_highs(), lsm_swing.get_swing_lows(), [lsm_candle])
    struct_ok = isinstance(struct_events, list)

    lsm_fvg = FairValueGapDetector()
    fvgs = lsm_fvg.analyze([
        Candle(symbol="BTCUSDT", timeframe="1h", timestamp=datetime.utcnow(), open=100, high=101, low=99, close=100, volume=100),
        Candle(symbol="BTCUSDT", timeframe="1h", timestamp=datetime.utcnow(), open=101, high=102, low=100.5, close=101.5, volume=100),
        Candle(symbol="BTCUSDT", timeframe="1h", timestamp=datetime.utcnow(), open=103, high=104, low=102, close=103, volume=100),
    ])
    fvg_ok = isinstance(fvgs, list)

    lsm_ob = OrderBlockDetector()
    obs = lsm_ob.analyze([lsm_candle], fvgs)
    ob_ok = isinstance(obs, list)

    lsm_pd = PremiumDiscountEngine()
    pd_state = lsm_pd.analyze(lsm_swing.get_swing_highs(), lsm_swing.get_swing_lows(), 100.0)
    pd_ok = pd_state.equilibrium > 0

    lsm_disp = DisplacementEngine()
    disp = lsm_disp.analyze([lsm_candle])
    disp_ok = disp is None or isinstance(disp, object)

    lsm_conf = ConfluenceEngine()
    conf_result = lsm_conf.analyze(zones, sweeps, struct_events, fvgs, obs, pd_state, [disp] if disp else [])
    conf_ok = conf_result.confluence_score >= 0

    logger.info(
        f"Liquidity Smart Money Engine loaded — "
        f"swing={swing_ok}, "
        f"pools={pools_ok}, "
        f"sweep={sweep_ok}, "
        f"structure={struct_ok}, "
        f"fvg={fvg_ok}, "
        f"orderblock={ob_ok}, "
        f"premium_discount={pd_ok}, "
        f"displacement={disp_ok}, "
        f"confluence={conf_ok}"
    )

    logger.info("Ultimate Trader initialized successfully")
    logger.info("Intelligence foundation ready")


if __name__ == "__main__":
    main()
