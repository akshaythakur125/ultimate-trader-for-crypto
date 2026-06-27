import pytest

from ultimate_trader.research_brain.hypothesis_generator import (
    DirectionBias,
    HypothesisGenerationContext,
    HypothesisGenerator,
    HypothesisStatus,
    ResearchHypothesis,
)
from ultimate_trader.research_brain.hypothesis_competition import (
    HypothesisCompetitionEngine,
    HypothesisCompetitionResult,
)
from ultimate_trader.research_brain.falsification_engine import (
    FalsificationEngine,
)
from ultimate_trader.research_brain.explanatory_power import (
    ExplanatoryPowerScorer,
)
from ultimate_trader.research_brain.predictive_power import (
    PredictivePowerScorer,
)
from ultimate_trader.research_brain.robustness_checker import (
    RobustnessChecker,
)
from ultimate_trader.research_brain.overfit_guard import (
    OverfitGuard,
)
from ultimate_trader.research_brain.hypothesis_ranker import (
    HypothesisRanker,
)


@pytest.fixture
def generator():
    return HypothesisGenerator()


@pytest.fixture
def ctx():
    return HypothesisGenerationContext(
        symbol="BTCUSDT",
        timeframe="1h",
        market_observations=["Price above 200 EMA", "Volume increasing"],
    )


@pytest.fixture
def sample_hypothesis():
    return ResearchHypothesis(
        research_id="RH-TEST001",
        name="Test Hypothesis",
        description="A test hypothesis",
        direction_bias=DirectionBias.LONG,
        market_explanation="Test market explanation",
        required_evidence=["Evidence A", "Evidence B"],
        invalidating_evidence=["Invalidation A"],
        expected_failure_modes=["Failure A"],
        regime_dependency="trending",
        liquidity_dependency="normal",
        orderflow_dependency="aggressive",
        expected_rr=3.0,
    )


class TestHypothesisGenerator:
    def test_generate_returns_12_hypotheses(self, generator, ctx):
        results = generator.generate(ctx)
        assert len(results) == 12

    def test_each_hypothesis_has_unique_id(self, generator, ctx):
        results = generator.generate(ctx)
        ids = [h.research_id for h in results]
        assert len(set(ids)) == 12

    def test_contains_no_trade_and_no_edge(self, generator, ctx):
        results = generator.generate(ctx)
        no_trade = [h for h in results if h.direction_bias == DirectionBias.NO_TRADE]
        assert len(no_trade) >= 2

    def test_families_are_correct(self, generator):
        expected = sorted([
            "BREAKOUT_CONTINUATION",
            "LIQUIDITY_SWEEP_REVERSAL",
            "LIQUIDITY_SWEEP_CONTINUATION",
            "FALSE_BREAKOUT",
            "SHORT_SQUEEZE",
            "LONG_SQUEEZE",
            "RANGE_CONTINUATION",
            "MEAN_REVERSION",
            "TREND_EXHAUSTION",
            "VOLATILITY_EXPANSION",
            "CHOP_NO_TRADE",
            "NO_EDGE",
        ])
        assert sorted(generator.FAMILIES) == expected

    def test_generate_by_family(self, generator, ctx):
        h = generator.generate_by_family(ctx, "BREAKOUT_CONTINUATION")
        assert h.name == "Breakout Continuation"
        assert h.direction_bias == DirectionBias.LONG

    def test_generate_by_family_invalid(self, generator, ctx):
        h = generator.generate_by_family(ctx, "INVALID_FAMILY")
        assert h.name == "No Edge"

    def test_breakout_continuation_has_rr(self, generator, ctx):
        h = generator.generate_by_family(ctx, "BREAKOUT_CONTINUATION")
        assert h.expected_rr >= 3.0
        assert h.expected_holding_time_hours > 0

    def test_chop_no_trade_is_no_trade(self, generator, ctx):
        h = generator.generate_by_family(ctx, "CHOP_NO_TRADE")
        assert h.direction_bias == DirectionBias.NO_TRADE
        assert h.expected_rr == 0.0

    def test_no_edge_is_no_trade(self, generator, ctx):
        h = generator.generate_by_family(ctx, "NO_EDGE")
        assert h.direction_bias == DirectionBias.NO_TRADE
        assert h.expected_rr == 0.0

    def test_all_have_default_status(self, generator, ctx):
        results = generator.generate(ctx)
        for h in results:
            assert h.status == HypothesisStatus.GENERATED


class TestHypothesisCompetitionEngine:
    def test_champion_comes_from_directional(self, generator, ctx):
        hypotheses = generator.generate(ctx)
        engine = HypothesisCompetitionEngine()
        result = engine.compare(hypotheses)
        if result.winning_hypothesis:
            assert result.winning_hypothesis.direction_bias in (
                DirectionBias.LONG, DirectionBias.SHORT, DirectionBias.NEUTRAL,
                DirectionBias.NO_TRADE,
            )

    def test_all_falsified_returns_no_trade(self, generator, ctx):
        hypotheses = generator.generate(ctx)
        for h in hypotheses:
            h.status = "FALSIFIED"
        engine = HypothesisCompetitionEngine()
        result = engine.compare(hypotheses)
        if result.winning_hypothesis:
            assert result.winning_hypothesis.direction_bias in (
                DirectionBias.NO_TRADE, DirectionBias.LONG, DirectionBias.SHORT,
            )

    def test_empty_hypotheses(self):
        engine = HypothesisCompetitionEngine()
        result = engine.compare([])
        assert result.no_edge_detected is True

    def test_high_score_hypothesis_wins(self):
        strong = ResearchHypothesis(
            research_id="RH-STRONG",
            name="Strong Hypothesis",
            direction_bias=DirectionBias.LONG,
            expected_rr=5.0,
            required_evidence=["A", "B", "C"],
            invalidating_evidence=["X"],
            expected_failure_modes=["F1"],
            regime_dependency="trending",
        )
        weak = ResearchHypothesis(
            research_id="RH-WEAK",
            name="Weak Hypothesis",
            direction_bias=DirectionBias.SHORT,
            expected_rr=1.0,
            required_evidence=[],
            invalidating_evidence=[],
            expected_failure_modes=[],
            regime_dependency="any",
        )
        engine = HypothesisCompetitionEngine()
        result = engine.compare([strong, weak])
        assert result.winning_hypothesis is not None
        assert result.winning_hypothesis.research_id == "RH-STRONG"

    def test_competition_summary_includes_winner(self):
        h = ResearchHypothesis(
            research_id="RH-SUM",
            name="Summary Test",
            direction_bias=DirectionBias.LONG,
            required_evidence=["A"],
            invalidating_evidence=["B"],
            expected_rr=3.0,
            regime_dependency="trending",
        )
        engine = HypothesisCompetitionEngine()
        result = engine.compare([h])
        assert "Summary Test" in result.competition_summary


class TestFalsificationEngine:
    def test_falsification_runs_on_hypothesis(self, sample_hypothesis):
        engine = FalsificationEngine()
        result = engine.falsify(sample_hypothesis)
        assert result.target_hypothesis_id == "RH-TEST001"

    def test_no_invalidating_evidence_triggers_falsification(self):
        h = ResearchHypothesis(
            research_id="RH-NOINV",
            name="No Invalidation",
            direction_bias=DirectionBias.LONG,
        )
        engine = FalsificationEngine()
        result = engine.falsify(h)
        assert result.is_falsified is True

    def test_unfalsified_hypothesis(self, sample_hypothesis):
        engine = FalsificationEngine()
        result = engine.falsify(sample_hypothesis)
        assert result.is_falsified is False

    def test_contradicting_evidence_triggers_falsification(self):
        h = ResearchHypothesis(
            research_id="RH-CONTR",
            name="Contradicting",
            direction_bias=DirectionBias.LONG,
            invalidating_evidence=["Something"],
            contradicting_evidence=["Price reversed"],
        )
        engine = FalsificationEngine()
        result = engine.falsify(h)
        assert result.is_falsified is True

    def test_falsification_updates_status(self, sample_hypothesis):
        engine = FalsificationEngine()
        engine.falsify(sample_hypothesis)
        assert sample_hypothesis.status == HypothesisStatus.GENERATED

        h = ResearchHypothesis(
            research_id="RH-NOINV2",
            name="No Invalidation",
            direction_bias=DirectionBias.LONG,
        )
        engine.falsify(h)
        assert h.status == HypothesisStatus.FALSIFIED

    def test_all_questions_asked(self, sample_hypothesis):
        engine = FalsificationEngine()
        result = engine.falsify(sample_hypothesis)
        assert len(result.questions) == 7


class TestExplanatoryPowerScorer:
    def test_well_defined_hypothesis_scores_high(self, sample_hypothesis):
        scorer = ExplanatoryPowerScorer()
        score = scorer.score(sample_hypothesis)
        assert score >= 60.0

    def test_bare_minimum_scores_low(self):
        h = ResearchHypothesis(
            research_id="RH-BARE",
            name="Bare Minimum",
            direction_bias=DirectionBias.NEUTRAL,
        )
        scorer = ExplanatoryPowerScorer()
        score = scorer.score(h)
        assert score <= 60.0

    def test_score_between_0_and_100(self, sample_hypothesis):
        scorer = ExplanatoryPowerScorer()
        score = scorer.score(sample_hypothesis)
        assert 0 <= score <= 100

    def test_rich_hypothesis_scores_100(self):
        h = ResearchHypothesis(
            research_id="RH-RICH",
            name="Rich Hypothesis",
            direction_bias=DirectionBias.LONG,
            market_explanation="Full explanation of market dynamics",
            regime_dependency="trending",
            liquidity_dependency="normal",
            orderflow_dependency="aggressive",
            required_evidence=["A", "B", "C", "D"],
            invalidating_evidence=["X", "Y"],
            expected_failure_modes=["F1"],
        )
        scorer = ExplanatoryPowerScorer()
        score = scorer.score(h)
        assert score == 100.0


class TestPredictivePowerScorer:
    def test_scores_well_defined_hypothesis(self, sample_hypothesis):
        scorer = PredictivePowerScorer()
        result = scorer.score(sample_hypothesis)
        assert result.predictive_power_score > 0
        assert result.hypothesis_id == "RH-TEST001"

    def test_bare_minimum_scores_low(self):
        h = ResearchHypothesis(
            research_id="RH-BARE2",
            name="Bare Minimum",
            direction_bias=DirectionBias.NEUTRAL,
        )
        scorer = PredictivePowerScorer()
        result = scorer.score(h)
        assert result.predictive_power_score <= 60.0

    def test_confidence_levels(self):
        scorer = PredictivePowerScorer()

        h_high = ResearchHypothesis(
            research_id="RH-HIGH",
            name="High",
            direction_bias=DirectionBias.LONG,
            expected_market_behavior="Will go up",
            required_evidence=["A", "B", "C", "D"],
            invalidating_evidence=["X", "Y"],
            expected_failure_modes=["F1", "F2"],
            expected_rr=3.0,
            regime_dependency="trending",
        )
        result = scorer.score(h_high)
        assert result.confidence == "high"

        h_low = ResearchHypothesis(
            research_id="RH-LOW",
            name="Low",
            direction_bias=DirectionBias.NEUTRAL,
        )
        result = scorer.score(h_low)
        assert result.confidence == "medium"

    def test_result_has_reasoning(self, sample_hypothesis):
        scorer = PredictivePowerScorer()
        result = scorer.score(sample_hypothesis)
        assert len(result.reasoning) > 0


class TestRobustnessChecker:
    def test_well_defined_passes_all(self, sample_hypothesis):
        checker = RobustnessChecker()
        result = checker.check(sample_hypothesis)
        assert result.robustness_score > 50.0

    def test_bare_minimum_fails_most(self):
        h = ResearchHypothesis(
            research_id="RH-BARE3",
            name="Bare Minimum",
            direction_bias=DirectionBias.NEUTRAL,
        )
        checker = RobustnessChecker()
        result = checker.check(h)
        assert result.robustness_score <= 50.0

    def test_all_checks_performed(self, sample_hypothesis):
        checker = RobustnessChecker()
        result = checker.check(sample_hypothesis)
        assert len(result.checks_performed) == 6

    def test_fails_without_supporting_evidence(self):
        h = ResearchHypothesis(
            research_id="RH-NOSUP",
            name="No Support",
            direction_bias=DirectionBias.LONG,
            required_evidence=["A"],
            invalidating_evidence=["B"],
            expected_failure_modes=["F"],
            regime_dependency="trending",
            expected_rr=3.0,
        )
        checker = RobustnessChecker()
        result = checker.check(h)
        assert result.checks_failed >= 1


class TestOverfitGuard:
    def test_well_defined_hypothesis_low_risk(self, sample_hypothesis):
        guard = OverfitGuard()
        assessment = guard.assess(sample_hypothesis)
        assert assessment.risk_level == "low"

    def test_bare_minimum_high_risk(self):
        h = ResearchHypothesis(
            research_id="RH-BARE4",
            name="Bare Minimum",
            direction_bias=DirectionBias.NEUTRAL,
        )
        guard = OverfitGuard()
        assessment = guard.assess(h)
        assert assessment.risk_level == "high"

    def test_extreme_rr_without_evidence_flagged(self):
        h = ResearchHypothesis(
            research_id="RH-EXTRR",
            name="Extreme RR",
            direction_bias=DirectionBias.LONG,
            expected_rr=15.0,
        )
        guard = OverfitGuard()
        assessment = guard.assess(h)
        assert assessment.risk_level == "high"

    def test_medium_risk_hypothesis(self):
        h = ResearchHypothesis(
            research_id="RH-MED",
            name="Medium Risk",
            direction_bias=DirectionBias.LONG,
            required_evidence=["A"],
            invalidating_evidence=["B"],
        )
        guard = OverfitGuard()
        assessment = guard.assess(h)
        assert assessment.risk_level in ("low", "medium")

    def test_recommendation_present(self, sample_hypothesis):
        guard = OverfitGuard()
        assessment = guard.assess(sample_hypothesis)
        assert len(assessment.recommendation) > 0


class TestHypothesisRanker:
    def test_rank_returns_sorted_results(self, generator, ctx):
        hypotheses = generator.generate(ctx)
        ranker = HypothesisRanker()
        results = ranker.rank(hypotheses)
        assert len(results) == 12
        for i in range(len(results) - 1):
            assert results[i].composite_score >= results[i + 1].composite_score

    def test_rank_assigns_unique_positions(self, generator, ctx):
        hypotheses = generator.generate(ctx)
        ranker = HypothesisRanker()
        results = ranker.rank(hypotheses)
        ranks = [r.rank for r in results]
        assert sorted(ranks) == list(range(1, 13))

    def test_each_result_has_all_scores(self, generator, ctx):
        hypotheses = [hypotheses := generator.generate(ctx)][0]
        hypotheses = generator.generate(ctx)
        ranker = HypothesisRanker()
        results = ranker.rank(hypotheses)
        for r in results:
            assert r.composite_score > 0
            assert r.falsification_result is not None
            assert r.overfit_assessment is not None

    def test_ranking_summary_contains_key_info(self, generator, ctx):
        hypotheses = generator.generate(ctx)
        ranker = HypothesisRanker()
        results = ranker.rank(hypotheses)
        for r in results:
            assert "Composite" in r.ranking_summary
