from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.core.constants import SignalStatus


class SignalCandidate(BaseModel):
    signal_id: str
    symbol: str
    exchange: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    estimated_rr: float
    confidence_score: float = Field(ge=0.0, le=100.0)
    risk_score: float = Field(ge=0.0, le=100.0)
    expected_holding_time_hours: float
    status: SignalStatus = SignalStatus.CANDIDATE
    rejection_reason: Optional[str] = None
