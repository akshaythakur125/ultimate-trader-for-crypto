from datetime import datetime, timedelta

from ultimate_trader.orderflow_intelligence.absorption_intelligence import (
    AbsorptionAnalysisResult,
    AbsorptionIntelligence,
)
from ultimate_trader.orderflow_intelligence.aggression_analyzer import (
    AggressionAnalysisResult,
    AggressionAnalyzer,
)
from ultimate_trader.orderflow_intelligence.delta_divergence import (
    DeltaDivergenceDetector,
    DeltaDivergenceResult,
)
from ultimate_trader.orderflow_intelligence.exhaustion_detector import (
    ExhaustionDetector,
    ExhaustionResult,
)
from ultimate_trader.orderflow_intelligence.flow_momentum import (
    FlowMomentumAnalyzer,
    FlowMomentumResult,
)
from ultimate_trader.orderflow_intelligence.iceberg_detector import (
    IcebergDetectionResult,
    IcebergDetector,
)
from ultimate_trader.orderflow_intelligence.institutional_report import (
    InstitutionalOrderFlowReport,
    TradePermission,
)
from ultimate_trader.orderflow_intelligence.models import (
    AbsorptionState,
    AggressionBias,
    AggressorSide,
    DeltaDivergenceType,
    ExhaustionState,
    FlowWindow,
    IcebergSuspicion,
    OrderFlowState,
    TradePrint,
    TradeSide,
    TrapAction,
    TrapRisk,
)
from ultimate_trader.orderflow_intelligence.orderflow_scenarios import (
    FlowScenario,
    OrderFlowScenarioEngine,
    OrderFlowScenarioReport,
)
from ultimate_trader.orderflow_intelligence.trade_flow import TradeFlowBuffer
from ultimate_trader.orderflow_intelligence.trap_detector import (
    TrapDetectionResult,
    TrapDetector,
)


NOW = datetime.utcnow()


def make_trade(side: AggressorSide, qty: float = 1.0, price: float = 100.0, ts=None) -> TradePrint:
    return TradePrint(
        symbol="BTCUSDT",
        timestamp=ts or NOW,
        price=price,
        quantity=qty,
        trade_value=price * qty,
        aggressor_side=side,
    )


def make_window(
    buy_vol: float = 0.0,
    sell_vol: float = 0.0,
    trades: list = None,
    cumulative_delta: float = 0.0,
    trade_count: int = 0,
    large_count: int = 0,
    total_value: float = 0.0,
) -> FlowWindow:
    return FlowWindow(
        symbol="BTCUSDT",
        total_buy_volume=buy_vol,
        total_sell_volume=sell_vol,
        trades=trades or [],
        cumulative_delta=cumulative_delta,
        trade_count=trade_count,
        large_trade_count=large_count,
        total_trade_value=total_value,
        buy_sell_delta=buy_vol - sell_vol,
    )


class TestTradeFlowBuffer:
    def test_add_and_get_window(self):
        buf = TradeFlowBuffer(window_seconds=60)
        buf.add_trade(make_trade(AggressorSide.BUYER, qty=2.0))
        buf.add_trade(make_trade(AggressorSide.SELLER, qty=1.0))
        window = buf.get_window("BTCUSDT")
        assert window.total_buy_volume == 2.0
        assert window.total_sell_volume == 1.0
        assert window.trade_count == 2

    def test_empty_window(self):
        buf = TradeFlowBuffer()
        window = buf.get_window("BTCUSDT")
        assert window.trade_count == 0
        assert window.total_buy_volume == 0.0

    def test_reset(self):
        buf = TradeFlowBuffer()
        buf.add_trade(make_trade(AggressorSide.BUYER))
        buf.reset()
        assert len(buf._trades) == 0


class TestAggressionAnalyzer:
    def test_buyer_aggression(self):
        analyzer = AggressionAnalyzer(aggression_threshold=0.6)
        window = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10)
        result = analyzer.analyze(window)
        assert result.aggression_bias == AggressionBias.BUYER_AGGRESSION
        assert result.buy_aggression_score == 80.0
        assert result.sell_aggression_score == 20.0

    def test_seller_aggression(self):
        analyzer = AggressionAnalyzer(aggression_threshold=0.6)
        window = make_window(buy_vol=30.0, sell_vol=70.0, trade_count=10)
        result = analyzer.analyze(window)
        assert result.aggression_bias == AggressionBias.SELLER_AGGRESSION

    def test_balanced(self):
        analyzer = AggressionAnalyzer(aggression_threshold=0.6)
        window = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10)
        result = analyzer.analyze(window)
        assert result.aggression_bias == AggressionBias.BALANCED

    def test_no_trades(self):
        analyzer = AggressionAnalyzer()
        window = make_window(trade_count=0)
        result = analyzer.analyze(window)
        assert result.aggression_bias == AggressionBias.UNKNOWN

    def test_large_trade_pressure_elevated(self):
        analyzer = AggressionAnalyzer(large_trade_threshold=0.3)
        window = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10, large_count=4)
        result = analyzer.analyze(window)
        assert result.large_trade_pressure == "elevated" or result.large_trade_pressure == "very_high"

    def test_large_trade_pressure_normal(self):
        analyzer = AggressionAnalyzer(large_trade_threshold=0.3)
        window = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10, large_count=1)
        result = analyzer.analyze(window)
        assert result.large_trade_pressure == "normal"

    def test_summary_has_all_fields(self):
        analyzer = AggressionAnalyzer()
        window = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=5, large_count=2)
        result = analyzer.analyze(window)
        assert result.aggression_summary
        assert "bias=" in result.aggression_summary
        assert "buy=" in result.aggression_summary


class TestAbsorptionIntelligence:
    def test_buying_absorbed(self):
        detector = AbsorptionIntelligence(absorption_ratio_threshold=0.65, price_stuck_threshold=0.1)
        window = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=5)
        result = detector.analyze(window, AggressionBias.BUYER_AGGRESSION, price_change_percent=0.05)
        assert result.absorption_detected is True
        assert result.absorption_type == AbsorptionState.BUYING_ABSORBED
        assert result.absorbed_side == "buyers"

    def test_selling_absorbed(self):
        detector = AbsorptionIntelligence()
        window = make_window(buy_vol=20.0, sell_vol=80.0, trade_count=5)
        result = detector.analyze(window, AggressionBias.SELLER_AGGRESSION, price_change_percent=0.05)
        assert result.absorption_detected is True
        assert result.absorption_type == AbsorptionState.SELLING_ABSORBED
        assert result.absorbed_side == "sellers"

    def test_no_absorption_when_price_moves(self):
        detector = AbsorptionIntelligence()
        window = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=5)
        result = detector.analyze(window, AggressionBias.BUYER_AGGRESSION, price_change_percent=1.0)
        assert result.absorption_detected is False

    def test_insufficient_trades(self):
        detector = AbsorptionIntelligence()
        window = make_window(buy_vol=10.0, sell_vol=5.0, trade_count=2)
        result = detector.analyze(window, AggressionBias.BALANCED)
        assert result.absorption_detected is False
        assert "Insufficient" in result.absorption_summary

    def test_no_volume(self):
        detector = AbsorptionIntelligence()
        window = make_window(trade_count=5)
        result = detector.analyze(window, AggressionBias.BALANCED)
        assert result.absorption_detected is False

    def test_reset(self):
        detector = AbsorptionIntelligence()
        window = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=5)
        detector.analyze(window, AggressionBias.BUYER_AGGRESSION, price_change_percent=0.05)
        detector.reset()
        assert len(detector._history) == 0


class TestExhaustionDetector:
    def test_insufficient_history(self):
        detector = ExhaustionDetector(history_length=10)
        window = make_window(buy_vol=100.0, sell_vol=50.0, trade_count=5)
        result = detector.analyze(window)
        assert result.exhaustion_detected is False
        assert "Insufficient" in result.exhaustion_reason

    def test_buyer_exhaustion(self):
        detector = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(3):
            detector.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trade_count=5))
        result = detector.analyze(make_window(buy_vol=30.0, sell_vol=50.0, trade_count=5))
        assert result.exhaustion_detected is True
        assert result.exhaustion_side == ExhaustionState.BUYER_EXHAUSTION

    def test_seller_exhaustion(self):
        detector = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(3):
            detector.analyze(make_window(buy_vol=50.0, sell_vol=100.0, trade_count=5))
        result = detector.analyze(make_window(buy_vol=50.0, sell_vol=20.0, trade_count=5))
        assert result.exhaustion_detected is True
        assert result.exhaustion_side == ExhaustionState.SELLER_EXHAUSTION

    def test_no_exhaustion(self):
        detector = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(5):
            detector.analyze(make_window(buy_vol=100.0, sell_vol=100.0, trade_count=5))
        result = detector.analyze(make_window(buy_vol=100.0, sell_vol=100.0, trade_count=5))
        assert result.exhaustion_detected is False

    def test_reset(self):
        detector = ExhaustionDetector()
        detector.analyze(make_window(trade_count=5))
        detector.reset()
        assert len(detector._history) == 0


class TestIcebergDetector:
    def test_insufficient_trades(self):
        detector = IcebergDetector(repeat_trade_threshold=3)
        trades = [make_trade(AggressorSide.BUYER, price=100.0) for _ in range(2)]
        window = make_window(trades=trades, trade_count=2)
        result = detector.analyze(window)
        assert result.iceberg_suspected == IcebergSuspicion.NONE

    def test_iceberg_detected(self):
        detector = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.BUYER, qty=1.0, price=100.0) for _ in range(5)]
        window = FlowWindow(
            symbol="BTCUSDT",
            trades=trades,
            trade_count=5,
            total_trade_value=500.0,
            total_buy_volume=5.0,
            total_sell_volume=2.0,
        )
        result = detector.analyze(window)
        assert result.iceberg_suspected in (IcebergSuspicion.LOW, IcebergSuspicion.MODERATE, IcebergSuspicion.HIGH)
        assert result.side == "buy"
        assert result.price_level > 0

    def test_no_repeat_pattern(self):
        detector = IcebergDetector(repeat_trade_threshold=3, price_proximity_percent=0.02)
        trades = [make_trade(AggressorSide.BUYER, qty=1.0, price=float(p)) for p in range(100, 106)]
        window = make_window(trades=trades, trade_count=6, total_value=600.0)
        result = detector.analyze(window)
        assert result.iceberg_suspected == IcebergSuspicion.NONE


class TestDeltaDivergence:
    def test_insufficient_history(self):
        detector = DeltaDivergenceDetector(history_length=10)
        window = make_window(cumulative_delta=10.0)
        result = detector.analyze(window, 100.0)
        assert result.divergence_detected is False
        assert "Insufficient" in result.interpretation

    def test_bullish_divergence(self):
        detector = DeltaDivergenceDetector(history_length=10)
        for price, delta in [(100.0, 10.0), (99.0, 12.0), (98.0, 15.0)]:
            detector.analyze(make_window(cumulative_delta=delta), price)
        result = detector.analyze(make_window(cumulative_delta=18.0), 97.0)
        assert result.divergence_detected is True
        assert result.divergence_type == DeltaDivergenceType.BULLISH_DIVERGENCE

    def test_bearish_divergence(self):
        detector = DeltaDivergenceDetector(history_length=10)
        for price, delta in [(100.0, 10.0), (101.0, 8.0), (102.0, 6.0)]:
            detector.analyze(make_window(cumulative_delta=delta), price)
        result = detector.analyze(make_window(cumulative_delta=4.0), 103.0)
        assert result.divergence_detected is True
        assert result.divergence_type == DeltaDivergenceType.BEARISH_DIVERGENCE

    def test_no_divergence(self):
        detector = DeltaDivergenceDetector(history_length=10)
        for price, delta in [(100.0, 10.0), (101.0, 12.0), (102.0, 14.0)]:
            detector.analyze(make_window(cumulative_delta=delta), price)
        result = detector.analyze(make_window(cumulative_delta=16.0), 103.0)
        assert result.divergence_detected is False

    def test_reset(self):
        detector = DeltaDivergenceDetector()
        detector.analyze(make_window(cumulative_delta=10.0), 100.0)
        detector.reset()
        assert len(detector._price_history) == 0
        assert len(detector._delta_history) == 0


class TestFlowMomentum:
    def test_insufficient_history(self):
        analyzer = FlowMomentumAnalyzer(history_length=10)
        window = make_window(trade_count=5)
        result = analyzer.analyze(window)
        assert result.flow_momentum_score == 50.0
        assert "Building" in result.summary

    def test_momentum_score_range(self):
        analyzer = FlowMomentumAnalyzer(history_length=10)
        for i in range(5):
            analyzer.analyze(make_window(buy_vol=50.0 + i * 10, sell_vol=50.0, trade_count=5))
        result = analyzer.analyze(make_window(buy_vol=90.0, sell_vol=50.0, trade_count=5))
        assert 0 <= result.flow_momentum_score <= 100
        assert result.acceleration in ("accelerating", "stable", "decelerating")
        assert result.persistence

    def test_reset(self):
        analyzer = FlowMomentumAnalyzer()
        analyzer.analyze(make_window(trade_count=5))
        analyzer.reset()
        assert len(analyzer._history) == 0


class TestTrapDetector:
    def test_long_trap(self):
        detector = TrapDetector()
        window = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=10, large_count=1)
        result = detector.analyze(
            window,
            AggressionBias.BUYER_AGGRESSION,
            AbsorptionState.BUYING_ABSORBED,
            "BEARISH_DIVERGENCE",
        )
        assert result.trap_detected is True
        assert result.trap_type == TrapRisk.LONG_TRAP_RISK
        assert result.recommended_action in (TrapAction.CAUTION, TrapAction.BLOCK_TRADE)

    def test_short_trap(self):
        detector = TrapDetector()
        window = make_window(buy_vol=30.0, sell_vol=70.0, trade_count=10, large_count=1)
        result = detector.analyze(
            window,
            AggressionBias.SELLER_AGGRESSION,
            AbsorptionState.SELLING_ABSORBED,
            "BULLISH_DIVERGENCE",
        )
        assert result.trap_detected is True
        assert result.trap_type == TrapRisk.SHORT_TRAP_RISK

    def test_no_trap(self):
        detector = TrapDetector()
        window = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=5)
        result = detector.analyze(
            window, AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, "NO_DIVERGENCE"
        )
        assert result.trap_detected is False
        assert result.trap_type == TrapRisk.LOW_TRAP_RISK

    def test_conflicting_signals(self):
        detector = TrapDetector()
        window = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=10, large_count=1)
        result = detector.analyze(
            window,
            AggressionBias.BUYER_AGGRESSION,
            AbsorptionState.SELLING_ABSORBED,
            "BULLISH_DIVERGENCE",
        )
        assert result.trap_detected is False
        assert result.recommended_action == TrapAction.WAIT

    def test_reset(self):
        detector = TrapDetector()
        detector.analyze(make_window(trade_count=5), AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, "NO_DIVERGENCE")
        detector.reset()
        assert len(detector._history) == 0


class TestOrderFlowScenarioEngine:
    def test_dominant_scenario_returned(self):
        engine = OrderFlowScenarioEngine()
        window = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=10, large_count=5)
        report = engine.analyze(
            window,
            AggressionBias.BUYER_AGGRESSION,
            AbsorptionState.NO_ABSORPTION,
            ExhaustionState.NO_EXHAUSTION,
            TrapRisk.LOW_TRAP_RISK,
        )
        assert report.dominant_scenario is not None
        assert len(report.scenarios) > 0
        assert report.no_edge_probability >= 0

    def test_no_edge_fallback(self):
        engine = OrderFlowScenarioEngine()
        window = make_window(trade_count=2)
        report = engine.analyze(
            window,
            AggressionBias.BALANCED,
            AbsorptionState.NO_ABSORPTION,
            ExhaustionState.NO_EXHAUSTION,
            TrapRisk.LOW_TRAP_RISK,
        )
        assert report.dominant_scenario == "no_edge_balanced_flow"

    def test_buyer_accumulation_scenario(self):
        engine = OrderFlowScenarioEngine()
        window = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10, large_count=5)
        report = engine.analyze(
            window,
            AggressionBias.BUYER_AGGRESSION,
            AbsorptionState.NO_ABSORPTION,
            ExhaustionState.NO_EXHAUSTION,
            TrapRisk.SHORT_TRAP_RISK,
        )
        assert report.dominant_scenario == "genuine_buyer_accumulation"

    def test_passive_seller_absorption_scenario(self):
        engine = OrderFlowScenarioEngine()
        window = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10)
        report = engine.analyze(
            window,
            AggressionBias.BUYER_AGGRESSION,
            AbsorptionState.BUYING_ABSORBED,
            ExhaustionState.NO_EXHAUSTION,
            TrapRisk.LONG_TRAP_RISK,
        )
        assert report.dominant_scenario == "passive_seller_absorption"

    def test_scenario_probabilities_summary(self):
        engine = OrderFlowScenarioEngine()
        window = make_window(buy_vol=60.0, sell_vol=40.0, trade_count=8)
        report = engine.analyze(
            window,
            AggressionBias.BUYER_AGGRESSION,
            AbsorptionState.BUYING_ABSORBED,
            ExhaustionState.NO_EXHAUSTION,
            TrapRisk.LOW_TRAP_RISK,
        )
        assert report.scenario_summary
        assert report.dominant_scenario in [s.name for s in report.scenarios]


class TestInstitutionalOrderFlowReport:
    def test_build_full_report(self):
        aggression = AggressionAnalysisResult(
            aggression_bias=AggressionBias.BUYER_AGGRESSION,
            buy_aggression_score=75.0,
            sell_aggression_score=25.0,
            large_trade_pressure="elevated",
            aggression_summary="test",
        )
        absorption = AbsorptionAnalysisResult(absorption_detected=False)
        exhaustion = ExhaustionResult(exhaustion_detected=False)
        iceberg = IcebergDetectionResult(iceberg_suspected=IcebergSuspicion.NONE)
        divergence = DeltaDivergenceResult(divergence_detected=False)
        momentum = FlowMomentumResult(flow_momentum_score=50.0, summary="test")
        trap = TrapDetectionResult(trap_detected=False, trap_type=TrapRisk.LOW_TRAP_RISK, recommended_action=TrapAction.WAIT)
        scenarios = OrderFlowScenarioReport(
            dominant_scenario="no_edge_balanced_flow",
            scenario_summary="test",
            no_edge_probability=50.0,
        )
        state = OrderFlowState(symbol="BTCUSDT")

        report = InstitutionalOrderFlowReport.build(
            symbol="BTCUSDT",
            aggression=aggression,
            absorption=absorption,
            exhaustion=exhaustion,
            iceberg=iceberg,
            divergence=divergence,
            momentum=momentum,
            trap=trap,
            scenarios=scenarios,
            state=state,
        )
        assert report.symbol == "BTCUSDT"
        assert report.trade_permission in (TradePermission.ALLOW, TradePermission.CAUTION, TradePermission.BLOCK)
        assert isinstance(report.final_summary, str)
        assert isinstance(report.reasons_to_avoid_trade, list)
        assert isinstance(report.reasons_supporting_trade, list)

    def test_trap_block_trade(self):
        aggression = AggressionAnalysisResult(aggression_bias=AggressionBias.BUYER_AGGRESSION)
        absorption = AbsorptionAnalysisResult(absorption_detected=False)
        exhaustion = ExhaustionResult(exhaustion_detected=False)
        iceberg = IcebergDetectionResult(iceberg_suspected=IcebergSuspicion.NONE)
        divergence = DeltaDivergenceResult(divergence_detected=False)
        momentum = FlowMomentumResult(flow_momentum_score=50.0, summary="test")
        trap = TrapDetectionResult(
            trap_detected=True,
            trap_type=TrapRisk.LONG_TRAP_RISK,
            trap_score=80.0,
            recommended_action=TrapAction.BLOCK_TRADE,
        )
        scenarios = OrderFlowScenarioReport(dominant_scenario="fake_breakout", scenario_summary="test")
        state = OrderFlowState(symbol="BTCUSDT")

        report = InstitutionalOrderFlowReport.build(
            symbol="BTCUSDT",
            aggression=aggression,
            absorption=absorption,
            exhaustion=exhaustion,
            iceberg=iceberg,
            divergence=divergence,
            momentum=momentum,
            trap=trap,
            scenarios=scenarios,
            state=state,
        )
        assert report.trade_permission == TradePermission.BLOCK
        assert len(report.reasons_to_avoid_trade) > 0

    def test_absorption_caution(self):
        aggression = AggressionAnalysisResult()
        absorption = AbsorptionAnalysisResult(absorption_detected=True, absorption_score=85.0)
        exhaustion = ExhaustionResult(exhaustion_detected=False)
        iceberg = IcebergDetectionResult(iceberg_suspected=IcebergSuspicion.NONE)
        divergence = DeltaDivergenceResult(divergence_detected=False)
        momentum = FlowMomentumResult(flow_momentum_score=50.0, summary="test")
        trap = TrapDetectionResult(trap_detected=False, trap_type=TrapRisk.LOW_TRAP_RISK, recommended_action=TrapAction.WAIT)
        scenarios = OrderFlowScenarioReport(scenario_summary="test")
        state = OrderFlowState(symbol="BTCUSDT")

        report = InstitutionalOrderFlowReport.build(
            symbol="BTCUSDT",
            aggression=aggression,
            absorption=absorption,
            exhaustion=exhaustion,
            iceberg=iceberg,
            divergence=divergence,
            momentum=momentum,
            trap=trap,
            scenarios=scenarios,
            state=state,
        )
        assert report.trade_permission == TradePermission.CAUTION

    def test_warning_flags_caution(self):
        aggression = AggressionAnalysisResult()
        absorption = AbsorptionAnalysisResult(absorption_detected=False)
        exhaustion = ExhaustionResult(exhaustion_detected=False)
        iceberg = IcebergDetectionResult(iceberg_suspected=IcebergSuspicion.NONE)
        divergence = DeltaDivergenceResult(divergence_detected=False)
        momentum = FlowMomentumResult(flow_momentum_score=50.0, summary="test")
        trap = TrapDetectionResult(trap_detected=False, trap_type=TrapRisk.LOW_TRAP_RISK, trap_score=10.0, recommended_action=TrapAction.WAIT)
        scenarios = OrderFlowScenarioReport(scenario_summary="test")
        state = OrderFlowState(symbol="BTCUSDT", warning_flags=["high_spread"])

        report = InstitutionalOrderFlowReport.build(
            symbol="BTCUSDT",
            aggression=aggression,
            absorption=absorption,
            exhaustion=exhaustion,
            iceberg=iceberg,
            divergence=divergence,
            momentum=momentum,
            trap=trap,
            scenarios=scenarios,
            state=state,
        )
        assert report.trade_permission == TradePermission.CAUTION
