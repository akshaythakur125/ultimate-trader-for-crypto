from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.research_brain.explanatory_power import (
    ExplanatoryPowerScorer,
)
from ultimate_trader.research_brain.falsification_engine import (
    FalsificationEngine,
    FalsificationResult,
)
from ultimate_trader.research_brain.hypothesis_generator import (
    ResearchHypothesis,
)
from ultimate_trader.research_brain.overfit_guard import (
    OverfitAssessment,
    OverfitGuard,
)
from ultimate_trader.research_brain.predictive_power import (
    PredictivePowerScore,
    PredictivePowerScorer,
)
from ultimate_trader.research_brain.robustness_checker import (
    RobustnessCheck,
    RobustnessChecker,
)


class HypothesisRankingResult(BaseModel):
    rank: int
    hypothesis: ResearchHypothesis
    composite_score: float
    explanatory_score: float = 0.0
    predictive_score: float = 0.0
    robustness_score: float = 0.0
    falsification_result: Optional[FalsificationResult] = None
    overfit_assessment: Optional[OverfitAssessment] = None
    ranking_summary: str = ""


class HypothesisRanker:
    def __init__(self):
        self._explanatory = ExplanatoryPowerScorer()
        self._predictive = PredictivePowerScorer()
        self._robustness = RobustnessChecker()
        self._falsification = FalsificationEngine()
        self._overfit = OverfitGuard()

    def rank(
        self,
        hypotheses: list[ResearchHypothesis],
    ) -> list[HypothesisRankingResult]:
        results: list[HypothesisRankingResult] = []

        for i, h in enumerate(hypotheses):
            explanatory_score = self._explanatory.score(h)
            predictive_result = self._predictive.score(h)
            robustness_result = self._robustness.check(h)
            falsification_result = self._falsification.falsify(h)
            overfit_assessment = self._overfit.assess(h)

            composite = (
                explanatory_score * 0.25
                + predictive_result.predictive_power_score * 0.25
                + robustness_result.robustness_score * 0.20
                + (100.0 - overfit_assessment.overfit_score) * 0.15
                + (0.0 if falsification_result.is_falsified else 100.0) * 0.15
            )

            results.append(
                HypothesisRankingResult(
                    rank=0,
                    hypothesis=h,
                    composite_score=composite,
                    explanatory_score=explanatory_score,
                    predictive_score=predictive_result.predictive_power_score,
                    robustness_score=robustness_result.robustness_score,
                    falsification_result=falsification_result,
                    overfit_assessment=overfit_assessment,
                    ranking_summary=(
                        f"Composite: {composite:.1f} | "
                        f"Expl: {explanatory_score:.0f} | "
                        f"Pred: {predictive_result.predictive_power_score:.0f} | "
                        f"Rob: {robustness_result.robustness_score:.0f} | "
                        f"Overfit: {overfit_assessment.risk_level} | "
                        + ("FALSIFIED" if falsification_result.is_falsified else "NOT FALSIFIED")
                    ),
                )
            )

        results.sort(key=lambda r: r.composite_score, reverse=True)
        for i, r in enumerate(results):
            r.rank = i + 1

        return results
