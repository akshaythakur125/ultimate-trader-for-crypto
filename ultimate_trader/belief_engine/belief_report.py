from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.belief_engine.belief_state import BeliefState
from ultimate_trader.belief_engine.decision_thresholds import DecisionThresholdResult
from ultimate_trader.belief_engine.expected_value import ExpectedValueResult
from ultimate_trader.belief_engine.market_belief import MarketBelief
from ultimate_trader.belief_engine.probability_calibrator import (
    ProbabilityCalibrationResult,
)
from ultimate_trader.belief_engine.risk_adjusted_utility import (
    RiskAdjustedUtilityResult,
)


class BeliefReport(BaseModel):
    report_id: str
    symbol: str
    timeframe: str
    belief_state: Optional[BeliefState] = None
    dominant_belief: Optional[MarketBelief] = None
    expected_value_result: Optional[ExpectedValueResult] = None
    risk_adjusted_utility_result: Optional[RiskAdjustedUtilityResult] = None
    probability_calibration: Optional[ProbabilityCalibrationResult] = None
    decision_threshold_result: Optional[DecisionThresholdResult] = None
    final_recommendation: str = "WAIT"
    explanation: str = ""
