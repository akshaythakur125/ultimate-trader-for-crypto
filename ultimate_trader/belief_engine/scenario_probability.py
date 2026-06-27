import math
import uuid
from typing import Optional

from ultimate_trader.belief_engine.belief_state import BeliefState
from ultimate_trader.belief_engine.evidence_likelihood import EvidenceLikelihood
from ultimate_trader.belief_engine.market_belief import BeliefStatus, DirectionBias, MarketBelief


class ScenarioProbabilityEngine:
    def initialize_default_beliefs(
        self,
        symbol: str,
        timeframe: str,
        direction_bias: DirectionBias = DirectionBias.LONG,
    ) -> BeliefState:
        beliefs = [
            MarketBelief(
                belief_id=f"BLF-{uuid.uuid4().hex[:8].upper()}",
                name="Breakout Continuation",
                description=f"{direction_bias.value} breakout continues in same direction",
                direction_bias=direction_bias,
                prior_probability=0.35,
                expected_rr_if_correct=3.0,
                expected_loss_r_if_wrong=1.0,
            ),
            MarketBelief(
                belief_id=f"BLF-{uuid.uuid4().hex[:8].upper()}",
                name="Liquidity Sweep Then Continuation",
                description="Price sweeps liquidity then continues in original direction",
                direction_bias=direction_bias,
                prior_probability=0.20,
                expected_rr_if_correct=4.0,
                expected_loss_r_if_wrong=1.5,
            ),
            MarketBelief(
                belief_id=f"BLF-{uuid.uuid4().hex[:8].upper()}",
                name="False Breakout",
                description="Breakout fails and reverses",
                direction_bias=DirectionBias.NEUTRAL,
                prior_probability=0.15,
                expected_rr_if_correct=2.0,
                expected_loss_r_if_wrong=1.0,
            ),
            MarketBelief(
                belief_id=f"BLF-{uuid.uuid4().hex[:8].upper()}",
                name="Reversal",
                description="Price reverses from current direction",
                direction_bias=DirectionBias.NEUTRAL,
                prior_probability=0.10,
                expected_rr_if_correct=3.5,
                expected_loss_r_if_wrong=1.0,
            ),
            MarketBelief(
                belief_id=f"BLF-{uuid.uuid4().hex[:8].upper()}",
                name="Range Continuation",
                description="Price continues ranging within established range",
                direction_bias=DirectionBias.NEUTRAL,
                prior_probability=0.10,
                expected_rr_if_correct=1.0,
                expected_loss_r_if_wrong=0.5,
            ),
            MarketBelief(
                belief_id=f"BLF-{uuid.uuid4().hex[:8].upper()}",
                name="Chop / No Trade",
                description="Market is choppy with no clear opportunity",
                direction_bias=DirectionBias.NO_TRADE,
                prior_probability=0.10,
            ),
        ]

        state = BeliefState(
            state_id=f"BST-{uuid.uuid4().hex[:8].upper()}",
            symbol=symbol,
            timeframe=timeframe,
            beliefs=beliefs,
        )
        state.normalize()
        return state

    def update_from_evidence(
        self,
        state: BeliefState,
        likelihoods: list[EvidenceLikelihood],
    ) -> BeliefState:
        from ultimate_trader.belief_engine.bayesian_updater import BayesianUpdater

        updater = BayesianUpdater()
        updated = updater.update_multiple(state.beliefs, likelihoods)
        state.beliefs = updated
        state.normalize()
        return state

    def calculate_entropy(self, state: BeliefState) -> float:
        return state._calculate_entropy()

    def identify_dominant_belief(self, state: BeliefState) -> Optional[MarketBelief]:
        return state.dominant_belief

    def reject_below_threshold(
        self,
        state: BeliefState,
        threshold: float = 0.05,
    ) -> BeliefState:
        for b in state.beliefs:
            prob = b.posterior_probability or b.prior_probability
            if prob < threshold:
                b.status = BeliefStatus.REJECTED
        state.normalize()
        return state
