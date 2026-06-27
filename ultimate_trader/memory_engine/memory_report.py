from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.memory_engine.confidence_calibrator import (
    ConfidenceCalibrationResult,
)
from ultimate_trader.memory_engine.similarity_engine import PatternSimilarityResult


class MemoryReport(BaseModel):
    report_id: str
    current_signature_id: str
    similar_cases_found: int = 0
    top_matches: list[PatternSimilarityResult] = Field(default_factory=list)
    historical_win_rate: float = 0.0
    historical_average_rr: float = 0.0
    historical_expectancy: float = 0.0
    success_patterns: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    regime_warning: str = ""
    confidence_calibration: Optional[ConfidenceCalibrationResult] = None
    final_memory_summary: str = ""
