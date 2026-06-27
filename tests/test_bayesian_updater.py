"""Tests for BayesianUpdater and BeliefState normalization."""

import uuid

from ultimate_trader.belief_engine.bayesian_updater import BayesianUpdater
from ultimate_trader.belief_engine.belief_state import BeliefState
from ultimate_trader.belief_engine.evidence_likelihood import EvidenceLikelihood
from ultimate_trader.belief_engine.market_belief import DirectionBias, MarketBelief


def _make_belief(
    belief_id: str,
    name: str,
    prior: float = 0.5,
    direction: DirectionBias = DirectionBias.LONG,
) -> MarketBelief:
    return MarketBelief(
        belief_id=belief_id,
        name=name,
        direction_bias=direction,
        prior_probability=prior,
    )


class TestBeliefState:
    def test_normalize_sums_to_one(self):
        state = BeliefState(
            state_id="BST-001",
            symbol="BTCUSDT",
            timeframe="1h",
            beliefs=[
                _make_belief("BLF-A", "Breakout", prior=0.4),
                _make_belief("BLF-B", "False Breakout", prior=0.3),
                _make_belief("BLF-C", "Reversal", prior=0.2),
                _make_belief("BLF-D", "No Trade", prior=0.1),
            ],
        )
        state.normalize()
        total = sum(b.posterior_probability for b in state.beliefs)
        assert abs(total - 1.0) < 0.02

    def test_dominant_belief_selected(self):
        state = BeliefState(
            state_id="BST-002",
            symbol="BTCUSDT",
            timeframe="1h",
            beliefs=[
                _make_belief("BLF-A", "Strong", prior=0.6),
                _make_belief("BLF-B", "Weak", prior=0.2),
                _make_belief("BLF-C", "No Trade", prior=0.2, direction=DirectionBias.NO_TRADE),
            ],
        )
        state.normalize()
        assert state.dominant_belief is not None
        assert state.dominant_belief.belief_id == "BLF-A"

    def test_no_trade_probability_calculated(self):
        state = BeliefState(
            state_id="BST-003",
            symbol="BTCUSDT",
            timeframe="1h",
            beliefs=[
                _make_belief("BLF-A", "Trade", prior=0.3),
                _make_belief("BLF-B", "No Trade", prior=0.7, direction=DirectionBias.NO_TRADE),
            ],
        )
        state.normalize()
        assert state.no_trade_probability > 0.5


class TestBayesianUpdater:
    def setup_method(self):
        self.updater = BayesianUpdater()

    def test_update_increases_with_supportive_evidence(self):
        posterior = self.updater.update(
            prior=0.5,
            likelihood_if_true=0.8,
            likelihood_if_false=0.2,
        )
        assert posterior > 0.5

    def test_update_decreases_with_contradictory_evidence(self):
        posterior = self.updater.update(
            prior=0.5,
            likelihood_if_true=0.2,
            likelihood_if_false=0.8,
        )
        assert posterior < 0.5

    def test_weak_reliability_smaller_update(self):
        strong = self.updater.update(
            prior=0.3, likelihood_if_true=0.9, likelihood_if_false=0.1, reliability=1.0
        )
        weak = self.updater.update(
            prior=0.3, likelihood_if_true=0.9, likelihood_if_false=0.1, reliability=0.2
        )
        diff_strong = abs(strong - 0.3)
        diff_weak = abs(weak - 0.3)
        assert diff_strong > diff_weak

    def test_posterior_clamped(self):
        posterior = self.updater.update(
            prior=0.999,
            likelihood_if_true=0.99,
            likelihood_if_false=0.01,
        )
        assert posterior <= 0.99

    def test_update_multiple_normalizes(self):
        beliefs = [
            _make_belief("BLF-A", "Breakout", prior=0.4),
            _make_belief("BLF-B", "False Breakout", prior=0.3),
            _make_belief("BLF-C", "No Trade", prior=0.3, direction=DirectionBias.NO_TRADE),
        ]
        likelihoods = [
            EvidenceLikelihood(
                evidence_id="EV-001",
                evidence_description="Volume spike",
                target_belief_id="BLF-A",
                likelihood_if_belief_true=0.8,
                likelihood_if_belief_false=0.2,
                reliability_score=0.9,
            ),
        ]
        updated = self.updater.update_multiple(beliefs, likelihoods)
        total = sum(b.posterior_probability or 0 for b in updated)
        assert abs(total - 1.0) < 0.02
