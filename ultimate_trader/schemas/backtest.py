from typing import Optional

from pydantic import BaseModel, Field


class BacktestSummary(BaseModel):
    hypothesis_id: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_rr: float = 0.0
    expectancy: float = 0.0
    max_drawdown_percent: float = 0.0
    max_daily_drawdown_percent: float = 0.0
    profit_factor: Optional[float] = None
    false_signal_rate: Optional[float] = None
    passed: bool = False
    failure_reason: Optional[str] = None
