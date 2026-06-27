"""Tests for all Pydantic schema contracts."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ultimate_trader.schemas.backtest import BacktestSummary
from ultimate_trader.schemas.decision import IntelligenceDecision
from ultimate_trader.schemas.explanation import SignalExplanation
from ultimate_trader.schemas.hypothesis import EvidenceBundle, TradingHypothesis
from ultimate_trader.schemas.learning import LearningReport
from ultimate_trader.schemas.market import (
    LiquidityAssessment,
    MarketRegimeAssessment,
    MarketSnapshot,
    OrderFlowAssessment,
)
from ultimate_trader.schemas.risk import RiskAssessment
from ultimate_trader.schemas.signal import SignalCandidate


class TestMarketSchema:
    def test_market_snapshot_minimal(self):
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            exchange="BingX",
            timeframe="1h",
            timestamp=datetime.now(timezone.utc),
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=1000.0,
        )
        assert snap.symbol == "BTCUSDT"
        assert snap.funding_rate is None

    def test_market_snapshot_full(self):
        snap = MarketSnapshot(
            symbol="ETHUSDT",
            exchange="BingX",
            timeframe="15m",
            timestamp=datetime.now(timezone.utc),
            open=3000.0,
            high=3100.0,
            low=2950.0,
            close=3050.0,
            volume=5000.0,
            funding_rate=0.0001,
            open_interest=1_000_000_000.0,
            spread=0.01,
            volatility=0.02,
            orderbook_imbalance=0.15,
            liquidation_intensity=0.3,
        )
        assert snap.funding_rate == 0.0001

    def test_market_regime_assessment(self):
        regime = MarketRegimeAssessment(
            symbol="BTCUSDT",
            timeframe="1h",
            regime_label="trending",
            trend_strength=0.8,
            volatility_state="low",
            compression_score=0.2,
            manipulation_risk=0.1,
        )
        assert regime.regime_label == "trending"

    def test_market_regime_invalid_trend_strength(self):
        with pytest.raises(ValidationError):
            MarketRegimeAssessment(
                symbol="BTCUSDT",
                timeframe="1h",
                regime_label="trending",
                trend_strength=1.5,
                volatility_state="low",
                compression_score=0.2,
                manipulation_risk=0.1,
            )


class TestLiquiditySchema:
    def test_liquidity_assessment_defaults(self):
        liq = LiquidityAssessment(symbol="BTCUSDT")
        assert liq.equal_highs_detected is False
        assert liq.key_liquidity_levels == []
        assert liq.manipulation_score == 0.0


class TestOrderFlowSchema:
    def test_orderflow_assessment_defaults(self):
        of = OrderFlowAssessment(symbol="BTCUSDT")
        assert of.orderflow_bias is None
        assert of.warning_flags == []


class TestHypothesisSchema:
    def test_trading_hypothesis_minimal(self):
        hyp = TradingHypothesis(
            hypothesis_id="HYP-001",
            name="Breakout Test",
            description="Test hypothesis",
            edge_theory="Momentum edge",
            expected_market_regime="trending",
            required_liquidity_condition="sweep",
            required_orderflow_condition="aggressive",
            expected_holding_time_hours=6.0,
            minimum_rr=3.0,
            preferred_rr=5.0,
            entry_logic_description="Entry when breakout confirmed",
            invalidation_logic_description="Invalidate on false breakout",
            expected_failure_conditions="Range expansion fails",
        )
        assert hyp.hypothesis_id == "HYP-001"
        assert hyp.status.value == "DRAFT"

    def test_evidence_bundle(self):
        eb = EvidenceBundle(
            evidence_for=["Volume spike", "Trend strength"],
            evidence_against=["Overbought RSI"],
            missing_evidence=["Order flow confirmation"],
            uncertainty_notes=["Low timeframe noise"],
        )
        assert len(eb.evidence_for) == 2


class TestDecisionSchema:
    def test_intelligence_decision(self):
        dec = IntelligenceDecision(
            decision_id="DEC-001",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            bias="NO_TRADE",
            long_probability=0.3,
            short_probability=0.2,
            confidence_score=45.0,
            risk_score=60.0,
            uncertainty_score=50.0,
            trade_quality_score=25.0,
            reasoning_summary="Insufficient evidence for a trade.",
        )
        assert dec.bias == "NO_TRADE"
        assert dec.requires_human_review is False


class TestSignalSchema:
    def test_signal_candidate(self):
        sig = SignalCandidate(
            signal_id="SIG-001",
            symbol="BTCUSDT",
            exchange="BingX",
            direction="LONG",
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit_1=52000.0,
            estimated_rr=3.0,
            confidence_score=75.0,
            risk_score=30.0,
            expected_holding_time_hours=6.0,
        )
        assert sig.status.value == "CANDIDATE"


class TestRiskSchema:
    def test_risk_assessment(self):
        risk = RiskAssessment(
            symbol="BTCUSDT",
            max_daily_drawdown_percent=10.0,
            position_risk_score=25.0,
            capital_at_risk_percent=2.0,
        )
        assert risk.trading_locked is False


class TestBacktestSchema:
    def test_backtest_summary(self):
        bt = BacktestSummary(
            hypothesis_id="HYP-001",
            total_trades=100,
            wins=65,
            losses=35,
            win_rate=0.65,
            average_rr=3.2,
            expectancy=1.8,
            max_drawdown_percent=8.5,
            max_daily_drawdown_percent=4.2,
            passed=True,
        )
        assert bt.passed is True

    def test_backtest_summary_failed(self):
        bt = BacktestSummary(
            hypothesis_id="HYP-002",
            total_trades=50,
            wins=20,
            losses=30,
            win_rate=0.40,
            average_rr=1.5,
            expectancy=-0.2,
            max_drawdown_percent=15.0,
            max_daily_drawdown_percent=12.0,
            passed=False,
            failure_reason="Win rate below 60% threshold",
        )
        assert bt.passed is False


class TestLearningSchema:
    def test_learning_report(self):
        report = LearningReport(
            report_id="LR-001",
            period_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2025, 1, 31, tzinfo=timezone.utc),
        )
        assert report.requires_human_approval is True


class TestExplanationSchema:
    def test_signal_explanation(self):
        expl = SignalExplanation(
            signal_id="SIG-001",
            core_reason="Strong trend with volume confirmation",
            invalidation="Price closes below entry range",
            why_trade_is_allowed="All conditions met",
            what_would_cancel_trade="Stop loss hit",
        )
        assert expl.signal_id == "SIG-001"
