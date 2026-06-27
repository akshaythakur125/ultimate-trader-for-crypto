import math
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.belief_engine.market_belief import MarketBelief


class BeliefState(BaseModel):
    state_id: str
    symbol: str
    timeframe: str
    timestamp: str = ""
    beliefs: list[MarketBelief] = Field(default_factory=list)
    dominant_belief: Optional[MarketBelief] = None
    entropy_score: float = 0.0
    conflict_score: float = 0.0
    uncertainty_score: float = 0.0
    no_trade_probability: float = 0.0
    state_summary: str = ""

    def normalize(self) -> None:
        total = sum(
            (b.posterior_probability or b.prior_probability)
            for b in self.beliefs
            if b.status != "REJECTED"
        )
        if total <= 0.0:
            equal = 1.0 / max(len(self.beliefs), 1)
            for b in self.beliefs:
                b.posterior_probability = equal
            return

        for b in self.beliefs:
            p = b.posterior_probability or b.prior_probability
            b.posterior_probability = max(0.01, min(0.99, p / total))

        remaining = 1.0 - sum(b.posterior_probability for b in self.beliefs)
        if abs(remaining) > 0.001:
            active = [b for b in self.beliefs if b.status != "REJECTED"]
            if active:
                adjustment = remaining / len(active)
                for b in active:
                    b.posterior_probability = max(
                        0.01, min(0.99, b.posterior_probability + adjustment)
                    )

        self.dominant_belief = max(
            [b for b in self.beliefs if b.status != "REJECTED"],
            key=lambda b: b.posterior_probability or 0,
            default=None,
        )
        self.entropy_score = self._calculate_entropy()
        self.no_trade_probability = sum(
            b.posterior_probability or 0
            for b in self.beliefs
            if b.direction_bias.value == "NO_TRADE"
        )
        self.uncertainty_score = self._calculate_uncertainty()

    def _calculate_entropy(self) -> float:
        probs = [
            b.posterior_probability or b.prior_probability
            for b in self.beliefs
            if b.status != "REJECTED" and (b.posterior_probability or b.prior_probability) > 0
        ]
        if not probs:
            return 0.0
        entropy = -sum(p * math.log2(p) for p in probs)
        max_entropy = math.log2(len(probs))
        if max_entropy == 0:
            return 0.0
        normalized = entropy / max_entropy
        return round(normalized * 100, 1)

    def _calculate_uncertainty(self) -> float:
        return self.entropy_score
