from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ultimate_trader.historical_replay.models import HistoricalCandle, TradeDirection


class FilterResult(BaseModel):
    filter_name: str
    passed: bool
    score: float = 0.0
    weight: float = 0.0
    weighted_score: float = 0.0
    data_available: bool = True
    reasoning: list[str] = Field(default_factory=list)


class StrategyConfig(BaseModel):
    confidence_threshold: float = 60.0
    direction: TradeDirection = TradeDirection.LONG
    weights: dict[str, float] = Field(default_factory=lambda: {
        "trend": 0.15,
        "structure": 0.12,
        "sweep": 0.10,
        "fvg": 0.08,
        "order_block": 0.08,
        "volume": 0.08,
        "orderflow": 0.10,
        "funding": 0.05,
        "open_interest": 0.05,
        "session": 0.04,
        "volatility": 0.07,
        "risk": 0.08,
    })
    ema_periods: list[int] = Field(default_factory=lambda: [20, 50, 100, 200])
    atr_period: int = 14
    volume_lookback: int = 20
    min_volume_ratio: float = 0.8
    max_risk_percent: float = 2.0
    atr_min_mult: float = 0.3
    atr_max_mult: float = 4.0
    session_allowed: bool = True
    max_concurrent_candidates: int = 1


class StrategyContext(BaseModel):
    candle: HistoricalCandle
    candles_history: list[HistoricalCandle] = Field(default_factory=list)
    direction: TradeDirection = TradeDirection.LONG
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    confluence_score: float = 0.0
    trade_permission: str = "ALLOW"
    lsm_swing_highs: list = Field(default_factory=list)
    lsm_swing_lows: list = Field(default_factory=list)
    lsm_sweeps: list = Field(default_factory=list)
    lsm_structure_events: list = Field(default_factory=list)
    lsm_fvgs: list = Field(default_factory=list)
    lsm_order_blocks: list = Field(default_factory=list)
    orderflow_data: Any = None
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    risk_score: float = 0.0


class StrategyCandidate(BaseModel):
    candidate_id: str
    symbol: str
    timeframe: str
    timestamp: datetime
    direction: TradeDirection
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    total_confidence: float = 0.0
    filter_results: dict[str, FilterResult] = Field(default_factory=dict)
    approved: bool = False
    rejection_reason: str = ""
    filters_passed: list[str] = Field(default_factory=list)
    filters_failed: list[str] = Field(default_factory=list)
    filters_unavailable: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class ComparisonResult(BaseModel):
    old_engine: str = "LSM Only"
    new_engine: str = "Strategy Engine"
    old_trades: int = 0
    new_trades: int = 0
    old_win_rate: float = 0.0
    new_win_rate: float = 0.0
    old_expectancy: float = 0.0
    new_expectancy: float = 0.0
    old_profit_factor: float = 0.0
    new_profit_factor: float = 0.0
    old_max_drawdown: float = 0.0
    new_max_drawdown: float = 0.0
    win_rate_change: float = 0.0
    expectancy_change: float = 0.0
    profit_factor_change: float = 0.0
    drawdown_change: float = 0.0
    improvement: str = ""
