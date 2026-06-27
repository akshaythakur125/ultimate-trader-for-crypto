"""Tests for belief engine models."""

import uuid

from ultimate_trader.belief_engine.market_belief import (
    BeliefStatus,
    DirectionBias,
    MarketBelief,
)


class TestMarketBelief:
    def test_belief_created(self):
        b = MarketBelief(
            belief_id="BLF-001",
            name="Test Belief",
            direction_bias=DirectionBias.LONG,
            prior_probability=0.5,
        )
        assert b.belief_id == "BLF-001"
        assert b.status == BeliefStatus.ACTIVE
        assert b.posterior_probability is None

    def test_belief_with_all_fields(self):
        b = MarketBelief(
            belief_id="BLF-002",
            name="Breakout",
            description="Test",
            direction_bias=DirectionBias.SHORT,
            prior_probability=0.3,
            posterior_probability=0.45,
            evidence_for=["Volume spike"],
            evidence_against=["Trend exhaustion"],
            expected_rr_if_correct=3.0,
            expected_loss_r_if_wrong=1.0,
            uncertainty_score=30.0,
            status=BeliefStatus.ACTIVE,
        )
        assert b.direction_bias == DirectionBias.SHORT
        assert b.expected_rr_if_correct == 3.0
