"""Tests for MemoryReport integration."""

import uuid

from ultimate_trader.memory_engine.case_library import CaseLibrary
from ultimate_trader.memory_engine.confidence_calibrator import ConfidenceCalibrator
from ultimate_trader.memory_engine.failure_memory import FailureMemory
from ultimate_trader.memory_engine.market_case import ActionTaken, MarketCase, OutcomeLabel
from ultimate_trader.memory_engine.memory_report import MemoryReport
from ultimate_trader.memory_engine.outcome_memory import OutcomeMemory
from ultimate_trader.memory_engine.pattern_signature import PatternSignature
from ultimate_trader.memory_engine.regime_memory import RegimeMemory
from ultimate_trader.memory_engine.similarity_engine import SimilarityEngine
from ultimate_trader.memory_engine.success_memory import SuccessMemory


def _make_case(
    regime: str = "trending",
    outcome: OutcomeLabel = OutcomeLabel.UNKNOWN,
    rr: float | None = None,
) -> MarketCase:
    return MarketCase(
        case_id=f"CASE-{uuid.uuid4().hex[:8].upper()}",
        timestamp="2024-01-01T00:00:00Z",
        symbol="BTCUSDT",
        timeframe="1h",
        pattern_signature=PatternSignature(
            signature_id=f"SIG-{uuid.uuid4().hex[:8].upper()}",
            symbol="BTCUSDT",
            timeframe="1h",
            regime_label=regime,
            liquidity_state="normal",
            orderflow_state="neutral",
            volatility_state="normal",
            trend_state="bullish",
        ),
        reasoning_summary="Test case",
        decision_bias="LONG",
        action_taken=ActionTaken.TRADE,
        outcome_known=outcome != OutcomeLabel.UNKNOWN,
        outcome_label=outcome,
        realized_rr=rr,
    )


class TestMemoryEngine:
    def setup_method(self):
        self.lib = CaseLibrary()
        self.sim_engine = SimilarityEngine()
        self.outcome = OutcomeMemory()
        self.failure = FailureMemory()
        self.success = SuccessMemory()
        self.regime = RegimeMemory()
        self.calibrator = ConfidenceCalibrator()

        for _ in range(5):
            self.lib.add_case(
                _make_case(
                    regime="trending",
                    outcome=OutcomeLabel.WIN,
                    rr=2.5,
                )
            )
        for _ in range(3):
            self.lib.add_case(
                _make_case(
                    regime="ranging",
                    outcome=OutcomeLabel.LOSS,
                    rr=-1.0,
                )
            )
        self.regime.build_from_cases(self.lib.list_cases())

    def test_memory_report_generated(self):
        current_sig = PatternSignature(
            signature_id="SIG-CURRENT",
            symbol="BTCUSDT",
            timeframe="1h",
            regime_label="trending",
            liquidity_state="normal",
            orderflow_state="neutral",
            volatility_state="normal",
            trend_state="bullish",
        )

        matches = self.sim_engine.find_similar_cases(
            current_sig, self.lib, min_similarity=70.0
        )
        all_cases = self.lib.list_cases()
        win_rate = self.outcome.calculate_win_rate(all_cases)
        avg_rr = self.outcome.calculate_average_rr(all_cases)
        expectancy = self.outcome.calculate_expectancy(all_cases)
        success_patterns = self.success.generate_success_support(
            current_sig, all_cases
        )
        failure_patterns = self.failure.generate_failure_warnings(
            current_sig, all_cases
        )
        regime_warning = self.regime.get_regime_warning(
            current_sig.regime_label
        )
        calibration = self.calibrator.calibrate(
            60.0, current_sig, all_cases
        )

        report = MemoryReport(
            report_id="MREP-001",
            current_signature_id=current_sig.signature_id,
            similar_cases_found=len(matches),
            top_matches=matches,
            historical_win_rate=round(win_rate, 1),
            historical_average_rr=round(avg_rr, 2),
            historical_expectancy=round(expectancy, 2),
            success_patterns=success_patterns,
            failure_patterns=failure_patterns,
            regime_warning=regime_warning,
            confidence_calibration=calibration,
            final_memory_summary=(
                f"Win rate: {win_rate:.0f}%, Avg R:R: {avg_rr:.1f}, "
                f"Calibrated confidence: {calibration.calibrated_confidence:.0f}"
            ),
        )

        assert report.report_id == "MREP-001"
        assert report.historical_win_rate > 0
        assert len(report.final_memory_summary) > 0
