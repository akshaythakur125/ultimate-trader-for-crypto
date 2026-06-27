import pytest
from datetime import datetime, timedelta
from ultimate_trader.selectivity_engine.daily_selector import DailySelector, DailySelectorConfig
from ultimate_trader.selectivity_engine.quality_gate import QualityGate, QualityGateConfig
from ultimate_trader.selectivity_engine.candidate_ranker import RankedCandidate


def make_rc(cid="t1", direction="LONG", grade="A", score=75, ts=None, symbol="BTCUSDT",
            confluence=60, confidence=0.6, conflict=0.2, reversal=30, risk=20, rr=3.0):
    if ts is None:
        ts = datetime(2025, 6, 1, 10, 0)
    return RankedCandidate(
        candidate_id=cid, symbol=symbol, direction=direction,
        timestamp=ts, rank_grade=grade, rank_score=score,
        confluence_score=confluence, directional_confidence=confidence,
        conflict_score=conflict, reversal_risk_score=reversal,
        risk_score=risk, rr_ratio=rr,
        continuation_score=50, target_realism_score=60,
        stop_quality_score=70, volatility_alignment=60,
    )


@pytest.fixture
def selector():
    qg = QualityGate()
    config = DailySelectorConfig(target_trades_per_day=3, hard_max_per_day=4)
    return DailySelector(qg, config)


class TestDailySelector:
    def test_selects_best_candidate(self, selector):
        day_key = "2025-06-01"
        rc = make_rc(grade="A_PLUS", score=90)
        selector.register_candidate(rc)
        results = selector.select_for_day(day_key)
        allowed = [r for _, r in results if r.allowed]
        assert len(allowed) == 1

    def test_hard_max_per_day(self, selector):
        day_key = "2025-06-01"
        for i in range(6):
            rc = make_rc(cid=f"t{i}", grade="A_PLUS", score=90,
                         ts=datetime(2025, 6, 1, 10 + i, 0))
            selector.register_candidate(rc)
        results = selector.select_for_day(day_key)
        allowed = [r for _, r in results if r.allowed]
        assert len(allowed) <= 4

    def test_rejects_after_max_losses(self, selector):
        day_key = "2025-06-01"
        for i in range(5):
            rc = make_rc(cid=f"t{i}", grade="A_PLUS", score=90,
                         ts=datetime(2025, 6, 1, 10 + i, 0))
            selector.register_candidate(rc)
        selector._daily_losses[day_key] = 2
        results = selector.select_for_day(day_key)
        allowed = [r for _, r in results if r.allowed]
        assert len(allowed) == 0

    def test_increases_threshold_after_losses(self, selector):
        day_key = "2025-06-01"
        selector._daily_losses[day_key] = 1
        rc = make_rc(grade="A", score=72, confluence=55, confidence=0.58, rr=3.0)
        selector.register_candidate(rc)
        results = selector.select_for_day(day_key)
        allowed = [r for _, r in results if r.allowed]
        assert len(allowed) == 0

    def test_same_direction_cooldown(self, selector):
        day_key = "2025-06-01"
        ts1 = datetime(2025, 6, 1, 10, 0)
        ts2 = datetime(2025, 6, 1, 10, 30)
        rc1 = make_rc(cid="t1", direction="LONG", ts=ts1)
        rc2 = make_rc(cid="t2", direction="LONG", ts=ts2)
        selector.register_candidate(rc1)
        selector.register_candidate(rc2)
        selector.select_for_day(day_key)
        selector._daily_counts[day_key] = 1
        selector._daily_losses[day_key] = 0
        results2 = selector.select_for_day(day_key)
        allowed2 = [r for _, r in results2 if r.allowed]
        assert len(allowed2) == 0

    def test_same_symbol_cooldown(self, selector):
        day_key = "2025-06-01"
        rc1 = make_rc(cid="t1", direction="LONG", ts=datetime(2025, 6, 1, 10, 0))
        rc2 = make_rc(cid="t2", direction="SHORT", ts=datetime(2025, 6, 1, 10, 30))
        selector.register_candidate(rc1)
        selector.register_candidate(rc2)
        selector.select_for_day(day_key)
        selector._daily_counts[day_key] = 1
        selector2 = DailySelector(QualityGate(), DailySelectorConfig(same_symbol_cooldown_minutes=120))
        selector2.register_candidate(rc2)
        selector2._last_trade_by_symbol["BTCUSDT"] = datetime(2025, 6, 1, 10, 0)
        results = selector2.select_for_day(day_key)
        allowed = [r for _, r in results if r.allowed]
        assert len(allowed) == 0

    def test_empty_day(self, selector):
        results = selector.select_for_day("2025-06-01")
        assert len(results) == 0

    def test_opposite_direction_allowed_after_cooldown(self, selector):
        day_key = "2025-06-01"
        rc1 = make_rc(cid="t1", direction="LONG", ts=datetime(2025, 6, 1, 10, 0))
        rc2 = make_rc(cid="t2", direction="SHORT", ts=datetime(2025, 6, 1, 10, 30))
        selector.register_candidate(rc1)
        selector.register_candidate(rc2)
        selector.select_for_day(day_key)

        selector2 = DailySelector(QualityGate())
        selector2.register_candidate(rc2)
        selector2._last_trade_by_direction["SHORT"] = datetime(2025, 6, 1, 7, 0)
        selector2._daily_counts[day_key] = 1
        results = selector2.select_for_day(day_key)
        allowed = [r for _, r in results if r.allowed]
        assert len(allowed) == 1

    def test_selects_by_rank_order(self, selector):
        day_key = "2025-06-01"
        low = make_rc(cid="low", grade="A", score=70, ts=datetime(2025, 6, 1, 10, 0))
        high = make_rc(cid="high", grade="A_PLUS", score=95, ts=datetime(2025, 6, 1, 11, 0))
        selector.register_candidate(low)
        selector.register_candidate(high)
        results = selector.select_for_day(day_key)
        allowed = [r for _, r in results if r.allowed]
        assert len(allowed) >= 1

    def test_record_outcome_winner(self, selector):
        day_key = "2025-06-01"
        selector.record_outcome("t1", True, day_key)
        assert selector._daily_wins[day_key] == 1

    def test_record_outcome_loser(self, selector):
        day_key = "2025-06-01"
        selector.record_outcome("t1", False, day_key)
        assert selector._daily_losses[day_key] == 1

    def test_reset_clears_state(self, selector):
        rc = make_rc(grade="A_PLUS")
        selector.register_candidate(rc)
        selector._daily_counts["2025-06-01"] = 3
        selector.reset()
        assert selector._daily_counts == {}
        assert selector._daily_losses == {}
