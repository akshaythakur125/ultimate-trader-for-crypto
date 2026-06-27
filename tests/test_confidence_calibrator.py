"""Tests for ConfidenceCalibrator."""

import uuid

from ultimate_trader.memory_engine.confidence_calibrator import ConfidenceCalibrator
from ultimate_trader.memory_engine.market_case import ActionTaken, MarketCase, OutcomeLabel
from ultimate_trader.memory_engine.pattern_signature import PatternSignature


def _make_case(
    outcome: OutcomeLabel = OutcomeLabel.UNKNOWN,
    rr: float | None = None,
    adverse_excursion: float | None = None,
    regime: str = "trending",
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
        reasoning_summary="Test",
        decision_bias="LONG",
        action_taken=ActionTaken.TRADE,
        outcome_known=outcome != OutcomeLabel.UNKNOWN,
        outcome_label=outcome,
        realized_rr=rr,
        max_adverse_excursion=adverse_excursion,
    )


def _make_sig(regime: str = "trending") -> PatternSignature:
    return PatternSignature(
        signature_id="SIG-CURRENT",
        symbol="BTCUSDT",
        timeframe="1h",
        regime_label=regime,
        liquidity_state="normal",
        orderflow_state="neutral",
        volatility_state="normal",
        trend_state="bullish",
    )


class TestConfidenceCalibrator:
    def setup_method(self):
        self.calibrator = ConfidenceCalibrator()

    def test_reduces_confidence_after_failures(self):
        sig = _make_sig()
        cases = [
            _make_case(outcome=OutcomeLabel.LOSS) for _ in range(4)
        ] + [
            _make_case(outcome=OutcomeLabel.WIN) for _ in range(1)
        ]
        result = self.calibrator.calibrate(80.0, sig, cases)
        assert result.calibrated_confidence < 80.0

    def test_increases_confidence_after_successes(self):
        sig = _make_sig()
        cases = [
            _make_case(outcome=OutcomeLabel.WIN, rr=3.0) for _ in range(4)
        ] + [
            _make_case(outcome=OutcomeLabel.LOSS) for _ in range(1)
        ]
        result = self.calibrator.calibrate(50.0, sig, cases)
        assert result.calibrated_confidence > 50.0

    def test_insufficient_memory(self):
        sig = _make_sig()
        cases = [
            _make_case(outcome=OutcomeLabel.WIN) for _ in range(1)
        ]
        result = self.calibrator.calibrate(
            70.0, sig, cases, min_memory_threshold=3
        )
        assert result.insufficient_memory is True
        assert result.calibrated_confidence < 70.0

    def test_adverse_excursion_increases_risk(self):
        sig = _make_sig()
        cases = [
            _make_case(
                outcome=OutcomeLabel.WIN, adverse_excursion=5.0
            ) for _ in range(3)
        ]
        result = self.calibrator.calibrate(50.0, sig, cases)
        assert result.calibrated_risk_score > 50.0

    def test_memory_support_score_reflects_win_rate(self):
        sig = _make_sig()
        cases = [
            _make_case(outcome=OutcomeLabel.WIN) for _ in range(8)
        ] + [
            _make_case(outcome=OutcomeLabel.LOSS) for _ in range(2)
        ]
        result = self.calibrator.calibrate(50.0, sig, cases)
        assert result.memory_support_score > 50.0

    def test_output_stays_in_bounds(self):
        sig = _make_sig()
        cases = [
            _make_case(outcome=OutcomeLabel.WIN, rr=5.0) for _ in range(10)
        ]
        result = self.calibrator.calibrate(100.0, sig, cases)
        assert result.calibrated_confidence <= 100.0
        assert result.calibrated_risk_score <= 100.0
