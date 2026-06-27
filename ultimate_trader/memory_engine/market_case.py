from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.memory_engine.pattern_signature import PatternSignature


class ActionTaken(str, Enum):
    TRADE = "TRADE"
    NO_TRADE = "NO_TRADE"
    WATCH = "WATCH"
    BACKTEST_ONLY = "BACKTEST_ONLY"


class OutcomeLabel(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    MISSED_WINNER = "MISSED_WINNER"
    CORRECT_NO_TRADE = "CORRECT_NO_TRADE"
    BAD_NO_TRADE = "BAD_NO_TRADE"
    UNKNOWN = "UNKNOWN"


class MarketCase(BaseModel):
    case_id: str
    timestamp: str
    symbol: str
    timeframe: str
    pattern_signature: PatternSignature
    reasoning_summary: str
    hypothesis_tested: Optional[str] = None
    decision_bias: str = ""
    action_taken: ActionTaken
    outcome_known: bool = False
    outcome_label: OutcomeLabel = OutcomeLabel.UNKNOWN
    realized_rr: Optional[float] = None
    max_favorable_excursion: Optional[float] = None
    max_adverse_excursion: Optional[float] = None
    holding_time_hours: Optional[float] = None
    failure_reason: Optional[str] = None
    success_reason: Optional[str] = None
    lessons: list[str] = Field(default_factory=list)
