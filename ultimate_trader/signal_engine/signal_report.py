from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.signal_gate import SignalGateResult
from ultimate_trader.signal_engine.signal_quality import (
    SignalQualityResult,
)
from ultimate_trader.signal_engine.trade_plan import TradePlan


class FinalRecommendation(str, Enum):
    ALERT_ONLY = "ALERT_ONLY"
    PAPER_TRADE_CANDIDATE = "PAPER_TRADE_CANDIDATE"
    REJECT_SIGNAL = "REJECT_SIGNAL"
    WAIT_FOR_ENTRY = "WAIT_FOR_ENTRY"
    NO_SAFE_ENTRY = "NO_SAFE_ENTRY"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class SignalReport(BaseModel):
    report_id: str
    signal_context: Optional[SignalContext] = None
    trade_plan: Optional[TradePlan] = None
    signal_quality: Optional[SignalQualityResult] = None
    signal_gate: Optional[SignalGateResult] = None
    final_recommendation: FinalRecommendation = FinalRecommendation.REJECT_SIGNAL
    explanation: str = ""
