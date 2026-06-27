from pydantic import BaseModel

from ultimate_trader.research_brain.hypothesis_generator import (
    ResearchHypothesis,
)


class ExplanatoryPowerScorer:
    def score(self, hypothesis: ResearchHypothesis) -> float:
        score = 50.0
        categories_covered = 0

        if hypothesis.regime_dependency and hypothesis.regime_dependency != "any":
            score += 10.0
            categories_covered += 1

        if hypothesis.liquidity_dependency and hypothesis.liquidity_dependency != "any":
            score += 5.0
            categories_covered += 1

        if hypothesis.orderflow_dependency and hypothesis.orderflow_dependency != "any":
            score += 5.0
            categories_covered += 1

        if hypothesis.required_evidence:
            score += min(len(hypothesis.required_evidence) * 5.0, 15.0)
            categories_covered += 1

        if hypothesis.market_explanation:
            score += 10.0
            categories_covered += 1

        if categories_covered >= 4:
            score += 10.0

        return min(100.0, max(0.0, score))
