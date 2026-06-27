from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LearningReport(BaseModel):
    report_id: str
    period_start: datetime
    period_end: datetime
    best_regimes: list[str] = Field(default_factory=list)
    worst_regimes: list[str] = Field(default_factory=list)
    best_symbols: list[str] = Field(default_factory=list)
    worst_symbols: list[str] = Field(default_factory=list)
    best_time_windows: list[str] = Field(default_factory=list)
    failed_patterns: list[str] = Field(default_factory=list)
    recommended_changes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_human_approval: bool = True
