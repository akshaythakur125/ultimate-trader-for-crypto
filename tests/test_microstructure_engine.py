from ultimate_trader.microstructure_engine.absorption_detector import (
    AbsorptionDetector,
)
from ultimate_trader.microstructure_engine.liquidity_voids import (
    LiquidityVoidDetector,
)
from ultimate_trader.microstructure_engine.microstructure_report import (
    MicrostructureReport,
)
from ultimate_trader.microstructure_engine.microstructure_state import (
    MicrostructureState,
)
from ultimate_trader.microstructure_engine.models import (
    AbsorptionSignal,
    ExecutionRisk,
    ImbalanceBias,
    OrderBookLevel,
    OrderBookSnapshot,
    SpoofingRiskLevel,
    SpoofingSignal,
    SpreadState,
    DepthState,
    TradePermission,
)
from ultimate_trader.microstructure_engine.orderbook_depth import (
    OrderBookDepthAnalyzer,
)
from ultimate_trader.microstructure_engine.orderbook_imbalance import (
    OrderBookImbalanceAnalyzer,
)
from ultimate_trader.microstructure_engine.price_impact import (
    PriceImpactEstimator,
)
from ultimate_trader.microstructure_engine.spoofing_risk import (
    SpoofingRiskDetector,
)
from ultimate_trader.microstructure_engine.spread_analysis import SpreadAnalyzer


def make_snapshot(
    bids: list = None,
    asks: list = None,
) -> OrderBookSnapshot:
    if bids is None:
        bids = [(100.0, 50), (99.9, 40), (99.8, 30), (99.7, 20), (99.6, 10)]
    if asks is None:
        asks = [(100.1, 50), (100.2, 40), (100.3, 30), (100.4, 20), (100.5, 10)]
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=p, quantity=q) for p, q in bids],
        asks=[OrderBookLevel(price=p, quantity=q) for p, q in asks],
    )


class TestOrderBookSnapshot:
    def test_best_bid_ask(self):
        snap = make_snapshot()
        assert snap.best_bid == 100.0
        assert snap.best_ask == 100.1

    def test_mid_price(self):
        snap = make_snapshot()
        assert snap.mid_price == 100.05

    def test_spread(self):
        snap = make_snapshot()
        import pytest
        assert snap.spread == pytest.approx(0.1, rel=1e-3)

    def test_spread_bps(self):
        snap = make_snapshot()
        expected = (0.1 / 100.05) * 10000
        assert abs(snap.spread_bps - expected) < 0.01

    def test_bid_depth(self):
        snap = make_snapshot()
        assert snap.bid_depth == 150.0

    def test_ask_depth(self):
        snap = make_snapshot()
        assert snap.ask_depth == 150.0

    def test_depth_imbalance_balanced(self):
        snap = make_snapshot()
        assert snap.depth_imbalance == 0.0

    def test_depth_imbalance_biased(self):
        snap = make_snapshot(bids=[(100.0, 100), (99.9, 50)], asks=[(100.1, 30)])
        assert snap.depth_imbalance > 0

    def test_empty_snapshot(self):
        snap = OrderBookSnapshot(symbol="BTCUSDT")
        assert snap.best_bid == 0.0
        assert snap.best_ask == 0.0
        assert snap.mid_price == 0.0
        assert snap.spread == 0.0
        assert snap.bid_depth == 0.0
        assert snap.ask_depth == 0.0


class TestSpreadAnalyzer:
    def test_normal_spread(self):
        analyzer = SpreadAnalyzer(wide_bps_threshold=100.0)
        snap = make_snapshot()
        state = analyzer.analyze(snap)
        assert state == SpreadState.NORMAL

    def test_wide_spread(self):
        analyzer = SpreadAnalyzer(wide_bps_threshold=1.0)
        snap = make_snapshot()
        state = analyzer.analyze(snap)
        assert state == SpreadState.WIDE

    def test_trade_blocking_spread(self):
        analyzer = SpreadAnalyzer(trade_blocking_bps_threshold=5.0)
        snap = make_snapshot()
        state = analyzer.analyze(snap)
        assert state == SpreadState.TRADE_BLOCKING

    def test_reset_clears_history(self):
        analyzer = SpreadAnalyzer()
        analyzer.analyze(make_snapshot())
        analyzer.reset()
        assert len(analyzer._history) == 0


class TestOrderBookDepthAnalyzer:
    def test_normal_depth(self):
        analyzer = OrderBookDepthAnalyzer(thin_book_quantity_threshold=10)
        snap = make_snapshot()
        state = analyzer.analyze(snap)
        assert state == DepthState.NORMAL

    def test_thin_book(self):
        analyzer = OrderBookDepthAnalyzer(thin_book_quantity_threshold=100)
        snap = make_snapshot(bids=[(100.0, 10)], asks=[(100.1, 50), (100.2, 60)])
        state = analyzer.analyze(snap)
        assert state == DepthState.THIN

    def test_critical_book(self):
        analyzer = OrderBookDepthAnalyzer(thin_book_quantity_threshold=100)
        snap = make_snapshot(bids=[(100.0, 5)], asks=[(100.1, 5)])
        state = analyzer.analyze(snap)
        assert state == DepthState.CRITICAL

    def test_liquidity_walls_detected(self):
        analyzer = OrderBookDepthAnalyzer(wall_quantity_threshold=30)
        snap = make_snapshot(
            bids=[(100.0, 100), (99.0, 50)],
            asks=[(101.0, 100), (102.0, 50)],
        )
        walls = analyzer.find_liquidity_walls(snap)
        assert len(walls["bid_walls"]) > 0
        assert len(walls["ask_walls"]) > 0

    def test_liquidity_walls_empty_when_below_threshold(self):
        analyzer = OrderBookDepthAnalyzer(wall_quantity_threshold=500)
        snap = make_snapshot()
        walls = analyzer.find_liquidity_walls(snap)
        assert len(walls["bid_walls"]) == 0
        assert len(walls["ask_walls"]) == 0

    def test_depth_imbalance_ratio_balanced(self):
        analyzer = OrderBookDepthAnalyzer()
        snap = make_snapshot()
        ratio = analyzer.get_depth_imbalance_ratio(snap)
        assert ratio == 0.0

    def test_depth_imbalance_ratio_imbalanced(self):
        analyzer = OrderBookDepthAnalyzer()
        snap = make_snapshot(bids=[(100.0, 100)], asks=[(100.1, 20)])
        ratio = analyzer.get_depth_imbalance_ratio(snap)
        assert ratio > 0


class TestOrderBookImbalanceAnalyzerIntegration:
    def test_bid_dominance_long(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snap = make_snapshot(bids=[(100.0, 100), (99.9, 50)], asks=[(100.1, 10)])
        result = analyzer.analyze(snap)
        assert result.bias == ImbalanceBias.LONG

    def test_ask_dominance_short(self):
        analyzer = OrderBookImbalanceAnalyzer()
        snap = make_snapshot(bids=[(100.0, 10)], asks=[(100.1, 100), (100.2, 50)])
        result = analyzer.analyze(snap)
        assert result.bias == ImbalanceBias.SHORT


class TestLiquidityVoidDetectorIntegration:
    def test_no_voids_adequate_book(self):
        detector = LiquidityVoidDetector()
        snap = make_snapshot()
        voids = detector.detect(snap)
        assert len(voids) == 0

    def test_voids_detected_with_gaps(self):
        detector = LiquidityVoidDetector(min_void_gap_bps=1.0)
        snap = make_snapshot(
            bids=[(100.0, 10)],
            asks=[(100.1, 1.0), (102.0, 0.5)],
        )
        voids = detector.detect(snap)
        assert len(voids) >= 1

    def test_voids_empty_book(self):
        detector = LiquidityVoidDetector()
        snap = OrderBookSnapshot(symbol="BTCUSDT")
        voids = detector.detect(snap)
        assert len(voids) == 0


class TestPriceImpactEstimatorIntegration:
    def test_small_order_ok(self):
        estimator = PriceImpactEstimator()
        snap = make_snapshot()
        result = estimator.estimate(snap, order_quantity=1.0)
        assert result.execution_risk in (ExecutionRisk.LOW, ExecutionRisk.MEDIUM)

    def test_huge_order_blocked(self):
        estimator = PriceImpactEstimator()
        snap = make_snapshot(bids=[(100.0, 1)], asks=[(100.1, 1)])
        result = estimator.estimate(snap, order_quantity=999.0)
        assert result.position_too_large is True


class TestAbsorptionDetectorIntegration:
    def test_absorption_not_detected_initial(self):
        detector = AbsorptionDetector(history_length=3)
        snap = make_snapshot()
        result = detector.analyze(snap)
        assert result.detected is False

    def test_reset_clears(self):
        detector = AbsorptionDetector()
        detector.analyze(make_snapshot())
        detector.reset()
        result = detector.analyze(make_snapshot())
        assert result.detected is False


class TestMicrostructureState:
    def test_default_allows_trade(self):
        state = MicrostructureState(symbol="BTCUSDT")
        assert state.trade_permission == TradePermission.ALLOW

    def test_trade_blocking_spread_blocks(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.TRADE_BLOCKING,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.LOW,
        )
        assert state.trade_permission == TradePermission.BLOCK

    def test_absorption_blocks(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.NORMAL,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=True, absorption_type="BUYING_ABSORBED_AT_RESISTANCE"),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.LOW,
        )
        assert state.trade_permission == TradePermission.BLOCK

    def test_spoofing_high_blocks(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.NORMAL,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=True, risk_level=SpoofingRiskLevel.HIGH),
            execution_risk=ExecutionRisk.LOW,
        )
        assert state.trade_permission == TradePermission.BLOCK

    def test_spoofing_low_with_wide_spread_cautions(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.WIDE,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=True, risk_level=SpoofingRiskLevel.LOW),
            execution_risk=ExecutionRisk.LOW,
        )
        assert state.trade_permission != TradePermission.ALLOW

    def test_multiple_warnings_caution(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.WIDE,
            depth_state=DepthState.THIN,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.HIGH,
        )
        assert state.trade_permission == TradePermission.CAUTION

    def test_critical_execution_blocks(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.NORMAL,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.CRITICAL,
        )
        assert state.trade_permission == TradePermission.BLOCK

    def test_reason_built(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.WIDE,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.LONG,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.MEDIUM,
        )
        assert len(state.reason) > 0
        assert "WIDE" in state.reason or "LONG" in state.reason


class TestMicrostructureReport:
    def test_report_created_from_state(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.NORMAL,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.LOW,
        )
        report = MicrostructureReport.from_state(
            report_id="MS-001", symbol="BTCUSDT", state=state,
        )
        assert report.report_id == "MS-001"
        assert report.symbol == "BTCUSDT"
        assert report.permission == TradePermission.ALLOW

    def test_report_includes_block_reasons(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.TRADE_BLOCKING,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.LOW,
        )
        report = MicrostructureReport.from_state(
            report_id="MS-002", symbol="BTCUSDT", state=state,
        )
        assert report.permission == TradePermission.BLOCK
        assert len(report.reasons_to_avoid) > 0

    def test_report_summary_present(self):
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.NORMAL,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.LONG,
            liquidity_voids=[],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.LOW,
        )
        report = MicrostructureReport.from_state(
            report_id="MS-003", symbol="BTCUSDT", state=state,
        )
        assert len(report.summary) > 0
        assert report.directional_bias == ImbalanceBias.LONG

    def test_reasons_to_avoid_for_voids(self):
        from ultimate_trader.microstructure_engine.models import LiquidityVoid
        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=SpreadState.NORMAL,
            depth_state=DepthState.NORMAL,
            imbalance_bias=ImbalanceBias.NEUTRAL,
            liquidity_voids=[LiquidityVoid(zone_label="void_test", price_above=101, price_below=100, depth_in_zone=0)],
            absorption=AbsorptionSignal(detected=False),
            spoofing=SpoofingSignal(detected=False),
            execution_risk=ExecutionRisk.LOW,
        )
        report = MicrostructureReport.from_state(
            report_id="MS-004", symbol="BTCUSDT", state=state,
        )
        assert any("void" in r.lower() for r in report.reasons_to_avoid)


class TestMicrostructureIntegration:
    def test_full_analysis_pipeline(self):
        snapshot = make_snapshot()
        spread_analyzer = SpreadAnalyzer()
        depth_analyzer = OrderBookDepthAnalyzer()
        imbalance_analyzer = OrderBookImbalanceAnalyzer()
        void_detector = LiquidityVoidDetector()
        price_estimator = PriceImpactEstimator()
        absorption_detector = AbsorptionDetector()
        spoofing_detector = SpoofingRiskDetector()

        spread_state = spread_analyzer.analyze(snapshot)
        depth_state = depth_analyzer.analyze(snapshot)
        imbalance = imbalance_analyzer.analyze(snapshot)
        voids = void_detector.detect(snapshot)
        impact = price_estimator.estimate(snapshot, 1.0)
        absorption = absorption_detector.analyze(snapshot)
        spoofing = spoofing_detector.analyze(snapshot)

        state = MicrostructureState(symbol="BTCUSDT")
        state.update(
            spread_state=spread_state,
            depth_state=depth_state,
            imbalance_bias=imbalance.bias,
            liquidity_voids=voids,
            absorption=absorption,
            spoofing=spoofing,
            execution_risk=impact.execution_risk,
        )

        report = MicrostructureReport.from_state(
            report_id="MS-FULL", symbol="BTCUSDT", state=state,
        )

        assert report.symbol == "BTCUSDT"
        assert report.permission in (TradePermission.ALLOW, TradePermission.CAUTION, TradePermission.BLOCK)
        assert len(report.summary) > 0

    def test_blocking_spread_in_pipeline(self):
        snapshot = make_snapshot()
        analyzer = SpreadAnalyzer(trade_blocking_bps_threshold=5.0)
        state = analyzer.analyze(snapshot)
        assert state == SpreadState.TRADE_BLOCKING

    def test_spoofing_detector_with_history(self):
        detector = SpoofingRiskDetector(history_length=3)
        snap = make_snapshot()
        for _ in range(4):
            detector.analyze(snap)
        result = detector.analyze(snap)
        assert hasattr(result, "detected")
        assert hasattr(result, "risk_level")
