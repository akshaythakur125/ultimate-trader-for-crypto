from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.signal_engine.signal_context import DirectionBias


class TradeStatus(str, Enum):
    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    READY_FOR_PAPER_TRADE = "READY_FOR_PAPER_TRADE"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class EntryType(str, Enum):
    LIMIT_ZONE = "LIMIT_ZONE"
    BREAKOUT_CONFIRMATION = "BREAKOUT_CONFIRMATION"
    PULLBACK_ENTRY = "PULLBACK_ENTRY"
    RECLAIM_ENTRY = "RECLAIM_ENTRY"
    RETEST_ENTRY = "RETEST_ENTRY"
    NO_SAFE_ENTRY = "NO_SAFE_ENTRY"


class EntryZone(BaseModel):
    entry_zone_id: str
    symbol: str
    direction: DirectionBias
    entry_min: float = 0.0
    entry_max: float = 0.0
    preferred_entry: float = 0.0
    entry_type: EntryType = EntryType.NO_SAFE_ENTRY
    entry_reason: str = ""
    maximum_acceptable_slippage_bps: float = 2.0
    maximum_acceptable_spread_bps: float = 5.0
    expires_after_candles: int = 12
    entry_invalid_if: str = ""


class StopType(str, Enum):
    STRUCTURE_INVALIDATION = "STRUCTURE_INVALIDATION"
    VOLATILITY_BASED = "VOLATILITY_BASED"
    LIQUIDITY_LEVEL_INVALIDATION = "LIQUIDITY_LEVEL_INVALIDATION"
    TIME_BASED_INVALIDATION = "TIME_BASED_INVALIDATION"


class StopPlan(BaseModel):
    stop_id: str
    stop_loss_price: float = 0.0
    stop_type: StopType = StopType.STRUCTURE_INVALIDATION
    stop_reason: str = ""
    distance_from_entry_percent: float = 0.0
    max_adverse_excursion_allowed_r: float = 1.0
    stop_is_too_obvious: bool = False
    stop_warning: Optional[str] = None


class TargetPlan(BaseModel):
    target_id: str
    take_profit_1: float = 0.0
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    target_reason: str = ""
    target_realism_score: float = 0.0
    nearby_obstacles: str = ""
    expected_reward_r: float = 0.0
    partial_exit_plan: Optional[str] = None


class RiskRewardAnalysis(BaseModel):
    rr_id: str
    entry_price: float = 0.0
    stop_loss_price: float = 0.0
    target_price: float = 0.0
    risk_per_unit: float = 0.0
    reward_per_unit: float = 0.0
    rr_ratio: float = 0.0
    meets_minimum_rr: bool = False
    meets_preferred_rr: bool = False
    rr_summary: str = ""


class ConditionType(str, Enum):
    REQUIRED = "REQUIRED"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


class ExecutionCondition(BaseModel):
    condition_id: str
    description: str
    condition_type: ConditionType = ConditionType.REQUIRED
    is_satisfied: bool = False
    failure_reason: Optional[str] = None


class CancellationRule(BaseModel):
    rule_id: str
    description: str
    cancel_if_triggered: bool = True
    reason: str = ""


class PositionSizingSuggestion(BaseModel):
    sizing_id: str
    account_equity: Optional[float] = None
    max_risk_percent: float = 1.0
    suggested_risk_percent: float = 1.0
    position_size_units: Optional[float] = None
    leverage_suggestion: Optional[int] = None
    sizing_reason: str = ""
    risk_warning: Optional[str] = None


class TradePlan(BaseModel):
    trade_plan_id: str
    symbol: str
    exchange: str = ""
    direction: DirectionBias
    timeframe: str
    entry_zone: Optional[EntryZone] = None
    stop_plan: Optional[StopPlan] = None
    target_plan: Optional[TargetPlan] = None
    rr_analysis: Optional[RiskRewardAnalysis] = None
    execution_conditions: list[ExecutionCondition] = Field(default_factory=list)
    cancellation_rules: list[CancellationRule] = Field(default_factory=list)
    position_sizing: Optional[PositionSizingSuggestion] = None
    expected_holding_time_hours: float = 0.0
    confidence_score: float = 0.0
    risk_score: float = 0.0
    uncertainty_score: float = 0.0
    expected_value_r: float = 0.0
    trade_status: TradeStatus = TradeStatus.DRAFT
    reasons_for_trade: list[str] = Field(default_factory=list)
    reasons_against_trade: list[str] = Field(default_factory=list)
    final_summary: str = ""
