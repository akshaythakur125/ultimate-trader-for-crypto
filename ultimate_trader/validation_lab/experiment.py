from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class TradingExperiment(BaseModel):
    experiment_id: str
    hypothesis_id: str
    hypothesis_name: str = ""
    experiment_name: str = ""
    description: str = ""
    symbol_universe: list[str] = Field(default_factory=list)
    timeframe: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    training_period: Optional[datetime] = None
    validation_period: Optional[datetime] = None
    out_of_sample_period: Optional[datetime] = None
    assumptions: list[str] = Field(default_factory=list)
    transaction_cost_model: str = "default"
    slippage_model: str = "default"
    funding_cost_model: str = "default"
    status: ExperimentStatus = ExperimentStatus.DRAFT
