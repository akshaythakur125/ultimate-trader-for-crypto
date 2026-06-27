"""Tests for OutcomeMemory, FailureMemory, SuccessMemory, RegimeMemory."""

import uuid

from ultimate_trader.memory_engine.failure_memory import FailureMemory
from ultimate_trader.memory_engine.market_case import ActionTaken, MarketCase, OutcomeLabel
from ultimate_trader.memory_engine.outcome_memory import OutcomeMemory
from ultimate_trader.memory_engine.pattern_signature import PatternSignature
from ultimate_trader.memory_engine.regime_memory import RegimeMemory
from ultimate_trader.memory_engine.success_memory import SuccessMemory


def _make_case(
    regime: str = "trending",
    outcome: OutcomeLabel = OutcomeLabel.UNKNOWN,
    rr: float | None = None,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    failure_reason: str | None = None,
    success_reason: str | None = None,
) -> MarketCase:
    return MarketCase(
        case_id=f"CASE-{uuid.uuid4().hex[:8].upper()}",
        timestamp="2024-01-01T00:00:00Z",
        symbol=symbol,
        timeframe=timeframe,
        pattern_signature=PatternSignature(
            signature_id=f"SIG-{uuid.uuid4().hex[:8].upper()}",
            symbol=symbol,
            timeframe=timeframe,
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
        failure_reason=failure_reason,
        success_reason=success_reason,
    )


class TestOutcomeMemory:
    def setup_method(self):
        self.memory = OutcomeMemory()

    def test_win_rate_all_wins(self):
        cases = [
            _make_case(outcome=OutcomeLabel.WIN) for _ in range(5)
        ]
        assert self.memory.calculate_win_rate(cases) == 100.0

    def test_win_rate_mixed(self):
        cases = [
            _make_case(outcome=OutcomeLabel.WIN) for _ in range(3)
        ] + [
            _make_case(outcome=OutcomeLabel.LOSS) for _ in range(2)
        ]
        assert self.memory.calculate_win_rate(cases) == 60.0

    def test_win_rate_no_resolved(self):
        cases = [
            _make_case(outcome=OutcomeLabel.UNKNOWN) for _ in range(3)
        ]
        assert self.memory.calculate_win_rate(cases) == 0.0

    def test_average_rr(self):
        cases = [
            _make_case(outcome=OutcomeLabel.WIN, rr=3.0),
            _make_case(outcome=OutcomeLabel.LOSS, rr=-1.0),
            _make_case(outcome=OutcomeLabel.WIN, rr=2.0),
        ]
        assert self.memory.calculate_average_rr(cases) == 4.0 / 3

    def test_expectancy_positive(self):
        cases = [
            _make_case(outcome=OutcomeLabel.WIN, rr=3.0),
            _make_case(outcome=OutcomeLabel.WIN, rr=2.0),
            _make_case(outcome=OutcomeLabel.LOSS, rr=-1.0),
        ]
        expectancy = self.memory.calculate_expectancy(cases)
        assert expectancy > 0

    def test_expectancy_no_rr(self):
        cases = [
            _make_case(outcome=OutcomeLabel.WIN, rr=None),
        ]
        assert self.memory.calculate_expectancy(cases) == 0.0

    def test_failure_rate(self):
        cases = [
            _make_case(outcome=OutcomeLabel.WIN) for _ in range(4)
        ] + [
            _make_case(outcome=OutcomeLabel.LOSS) for _ in range(1)
        ]
        assert self.memory.calculate_failure_rate(cases) == 20.0

    def test_summarize_by_regime(self):
        cases = [
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
            _make_case(regime="trending", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.WIN),
        ]
        summary = self.memory.summarize_outcomes_by_regime(cases)
        assert "trending" in summary
        assert summary["trending"]["total"] == 2
        assert summary["trending"]["wins"] == 1

    def test_summarize_by_symbol(self):
        cases = [
            _make_case(symbol="BTCUSDT", outcome=OutcomeLabel.WIN),
            _make_case(symbol="ETHUSDT", outcome=OutcomeLabel.LOSS),
        ]
        summary = self.memory.summarize_outcomes_by_symbol(cases)
        assert "BTCUSDT" in summary
        assert "ETHUSDT" in summary

    def test_summarize_by_timeframe(self):
        cases = [
            _make_case(timeframe="1h", outcome=OutcomeLabel.WIN),
            _make_case(timeframe="15m", outcome=OutcomeLabel.LOSS),
        ]
        summary = self.memory.summarize_outcomes_by_timeframe(cases)
        assert "1h" in summary
        assert "15m" in summary


class TestFailureMemory:
    def setup_method(self):
        self.memory = FailureMemory()

    def test_identify_common_failure_reasons(self):
        cases = [
            _make_case(
                outcome=OutcomeLabel.LOSS, failure_reason="Poor entry timing"
            ),
            _make_case(
                outcome=OutcomeLabel.LOSS, failure_reason="Poor entry timing"
            ),
            _make_case(
                outcome=OutcomeLabel.LOSS, failure_reason="Stop too tight"
            ),
        ]
        reasons = self.memory.identify_common_failure_reasons(cases)
        assert len(reasons) >= 2
        assert reasons[0][0] == "Poor entry timing"

    def test_identify_regimes_with_high_failure(self):
        cases = [
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.WIN),
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
        ]
        regimes = self.memory.identify_regimes_with_high_failure(cases)
        assert regimes[0][0] == "ranging"

    def test_generate_failure_warnings(self):
        target_sig = _make_case(
            regime="ranging", outcome=OutcomeLabel.LOSS
        ).pattern_signature
        similar = [
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.WIN),
        ]
        warnings = self.memory.generate_failure_warnings(target_sig, similar)
        assert len(warnings) > 0


class TestSuccessMemory:
    def setup_method(self):
        self.memory = SuccessMemory()

    def test_identify_common_success_reasons(self):
        cases = [
            _make_case(
                outcome=OutcomeLabel.WIN, success_reason="Strong trend follow"
            ),
            _make_case(
                outcome=OutcomeLabel.WIN, success_reason="Strong trend follow"
            ),
            _make_case(
                outcome=OutcomeLabel.WIN, success_reason="Good risk management"
            ),
        ]
        reasons = self.memory.identify_common_success_reasons(cases)
        assert reasons[0][0] == "Strong trend follow"

    def test_identify_regimes_with_high_success(self):
        cases = [
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
            _make_case(regime="trending", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
        ]
        regimes = self.memory.identify_regimes_with_high_success(cases)
        assert regimes[0][0] == "trending"

    def test_generate_success_support(self):
        target_sig = _make_case(
            regime="trending", outcome=OutcomeLabel.WIN
        ).pattern_signature
        similar = [
            _make_case(regime="trending", outcome=OutcomeLabel.WIN, rr=3.0),
            _make_case(regime="trending", outcome=OutcomeLabel.WIN, rr=2.5),
            _make_case(regime="trending", outcome=OutcomeLabel.LOSS),
        ]
        support = self.memory.generate_success_support(target_sig, similar)
        assert len(support) > 0


class TestRegimeMemory:
    def setup_method(self):
        self.memory = RegimeMemory()

    def test_build_from_cases(self):
        cases = [
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
            _make_case(regime="trending", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
        ]
        self.memory.build_from_cases(cases)
        assert "trending" in self.memory.regime_success_map
        assert "ranging" in self.memory.regime_failure_map

    def test_get_best_regimes(self):
        cases = [
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="volatile", outcome=OutcomeLabel.WIN),
        ]
        self.memory.build_from_cases(cases)
        best = self.memory.get_best_regimes()
        assert len(best) > 0
        assert best[0][1] >= 50.0

    def test_get_dangerous_regimes(self):
        cases = [
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="ranging", outcome=OutcomeLabel.LOSS),
            _make_case(regime="trending", outcome=OutcomeLabel.WIN),
        ]
        self.memory.build_from_cases(cases)
        dangerous = self.memory.get_dangerous_regimes()
        assert dangerous[0][0] == "ranging"

    def test_get_regime_warning_dangerous(self):
        self.memory.regime_failure_map["ranging"] = 80.0
        warning = self.memory.get_regime_warning("ranging")
        assert "DANGEROUS" in warning

    def test_get_regime_warning_unknown(self):
        warning = self.memory.get_regime_warning("unknown_regime")
        assert "UNKNOWN" in warning
