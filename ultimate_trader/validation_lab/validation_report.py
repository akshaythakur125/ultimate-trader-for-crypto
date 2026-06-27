from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.validation_lab.backtest_protocol import BacktestProtocol
from ultimate_trader.validation_lab.dataset_splitter import DatasetSplit
from ultimate_trader.validation_lab.experiment import TradingExperiment
from ultimate_trader.validation_lab.monte_carlo import MonteCarloResult
from ultimate_trader.validation_lab.out_of_sample import OutOfSampleResult
from ultimate_trader.validation_lab.performance_metrics import (
    PerformanceMetrics,
)
from ultimate_trader.validation_lab.sensitivity_analysis import (
    SensitivityResult,
)
from ultimate_trader.validation_lab.validation_gate import (
    ValidationGateResult,
)
from ultimate_trader.validation_lab.walk_forward import WalkForwardResult


class RecommendedNextAction(str, Enum):
    REJECT_HYPOTHESIS = "REJECT_HYPOTHESIS"
    IMPROVE_HYPOTHESIS = "IMPROVE_HYPOTHESIS"
    COLLECT_MORE_DATA = "COLLECT_MORE_DATA"
    PAPER_TEST_ONLY = "PAPER_TEST_ONLY"
    READY_FOR_SIGNAL_GENERATION = "READY_FOR_SIGNAL_GENERATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ValidationReport(BaseModel):
    report_id: str
    experiment: Optional[TradingExperiment] = None
    dataset_split: Optional[DatasetSplit] = None
    backtest_protocol: Optional[BacktestProtocol] = None
    performance_metrics: Optional[PerformanceMetrics] = None
    walk_forward_result: Optional[WalkForwardResult] = None
    out_of_sample_result: Optional[OutOfSampleResult] = None
    monte_carlo_result: Optional[MonteCarloResult] = None
    sensitivity_result: Optional[SensitivityResult] = None
    validation_gate_result: Optional[ValidationGateResult] = None
    final_conclusion: str = ""
    recommended_next_action: RecommendedNextAction = RecommendedNextAction.IMPROVE_HYPOTHESIS
