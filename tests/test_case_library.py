"""Tests for CaseLibrary and MarketCase."""

import uuid

from ultimate_trader.memory_engine.case_library import CaseLibrary
from ultimate_trader.memory_engine.market_case import (
    ActionTaken,
    MarketCase,
    OutcomeLabel,
)
from ultimate_trader.memory_engine.pattern_signature import PatternSignature


def _make_case(
    case_id: str = "",
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    regime: str = "trending",
    outcome: OutcomeLabel = OutcomeLabel.UNKNOWN,
) -> MarketCase:
    return MarketCase(
        case_id=case_id or f"CASE-{uuid.uuid4().hex[:8].upper()}",
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
    )


class TestMarketCase:
    def test_case_created(self):
        case = _make_case(case_id="CASE-001")
        assert case.case_id == "CASE-001"
        assert case.action_taken == ActionTaken.TRADE

    def test_case_with_outcome(self):
        case = _make_case(
            case_id="CASE-002",
            outcome=OutcomeLabel.WIN,
        )
        case.realized_rr = 3.5
        assert case.outcome_label == OutcomeLabel.WIN
        assert case.realized_rr == 3.5
        assert case.outcome_known is True


class TestCaseLibrary:
    def setup_method(self):
        self.lib = CaseLibrary()

    def test_add_and_get_case(self):
        case = _make_case(case_id="CASE-001")
        self.lib.add_case(case)
        retrieved = self.lib.get_case("CASE-001")
        assert retrieved is not None
        assert retrieved.case_id == "CASE-001"

    def test_list_cases(self):
        self.lib.add_case(_make_case(case_id="CASE-A"))
        self.lib.add_case(_make_case(case_id="CASE-B"))
        assert len(self.lib.list_cases()) == 2

    def test_filter_by_symbol(self):
        self.lib.add_case(_make_case(case_id="CASE-1", symbol="BTCUSDT"))
        self.lib.add_case(_make_case(case_id="CASE-2", symbol="ETHUSDT"))
        self.lib.add_case(_make_case(case_id="CASE-3", symbol="BTCUSDT"))
        assert len(self.lib.filter_by_symbol("BTCUSDT")) == 2
        assert len(self.lib.filter_by_symbol("ETHUSDT")) == 1

    def test_filter_by_regime(self):
        self.lib.add_case(_make_case(case_id="CASE-1", regime="trending"))
        self.lib.add_case(_make_case(case_id="CASE-2", regime="ranging"))
        assert len(self.lib.filter_by_regime("trending")) == 1

    def test_filter_by_outcome(self):
        self.lib.add_case(
            _make_case(case_id="CASE-1", outcome=OutcomeLabel.WIN)
        )
        self.lib.add_case(
            _make_case(case_id="CASE-2", outcome=OutcomeLabel.LOSS)
        )
        self.lib.add_case(
            _make_case(case_id="CASE-3", outcome=OutcomeLabel.WIN)
        )
        assert len(self.lib.filter_by_outcome(OutcomeLabel.WIN)) == 2
        assert len(self.lib.filter_by_outcome(OutcomeLabel.LOSS)) == 1

    def test_filter_by_timeframe(self):
        self.lib.add_case(_make_case(case_id="CASE-1", timeframe="1h"))
        self.lib.add_case(_make_case(case_id="CASE-2", timeframe="15m"))
        assert len(self.lib.filter_by_timeframe("1h")) == 1

    def test_success_cases(self):
        self.lib.add_case(
            _make_case(case_id="CASE-1", outcome=OutcomeLabel.WIN)
        )
        self.lib.add_case(
            _make_case(case_id="CASE-2", outcome=OutcomeLabel.LOSS)
        )
        assert len(self.lib.get_success_cases()) == 1

    def test_failure_cases(self):
        self.lib.add_case(
            _make_case(case_id="CASE-1", outcome=OutcomeLabel.LOSS)
        )
        self.lib.add_case(
            _make_case(case_id="CASE-2", outcome=OutcomeLabel.BAD_NO_TRADE)
        )
        assert len(self.lib.get_failure_cases()) == 2

    def test_count(self):
        assert self.lib.count() == 0
        self.lib.add_case(_make_case(case_id="CASE-1"))
        assert self.lib.count() == 1
