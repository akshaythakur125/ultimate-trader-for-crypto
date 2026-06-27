from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.research_brain.hypothesis_generator import (
    ResearchHypothesis,
)
from ultimate_trader.research_brain.hypothesis_ranker import (
    HypothesisRankingResult,
)


class ResearchReport(BaseModel):
    report_id: str
    symbol: str
    timeframe: str
    generated_hypotheses: list[ResearchHypothesis] = Field(default_factory=list)
    ranked_results: list[HypothesisRankingResult] = Field(default_factory=list)
    competition_result: Optional[dict] = None
    winning_recommendation: Optional[str] = None
    research_summary: str = ""
    risk_warning: str = ""
    decision: Optional[str] = None
