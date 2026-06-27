import pytest
from datetime import datetime
from ultimate_trader.selectivity_engine.candidate_ranker import CandidateRanker, RankedCandidate, RANK_GRADES


class DummyCandidate:
    def __init__(self, direction="LONG", entry=50000, target=51500, stop=49500):
        self.candidate_id = "dummy_1"
        self.symbol = "BTCUSDT"
        self.direction = direction
        self.timestamp = datetime(2025, 6, 1, 10, 0)
        self.entry_price = entry
        self.target_price = target
        self.stop_loss = stop


class DummyConfluence:
    def __init__(self, score=70, confidence=0.7, conflict=0.2, reversal=30, continuation=60, reasons_for=None):
        self.confluence_score = score
        self.directional_confidence = confidence
        self.conflict_score = conflict
        self.reversal_risk_score = reversal
        self.continuation_score = continuation
        self.reasons_for = reasons_for or []


class TestCandidateRanker:
    def test_rank_a_plus_candidate(self):
        ranker = CandidateRanker()
        cand = DummyCandidate()
        conf = DummyConfluence(score=85, confidence=0.85, conflict=0.1, reversal=20, continuation=70,
                                reasons_for=["liquidity sweep detected", "order flow confirmation", "strong sweep at high"])
        rc = ranker.rank(cand, conf)
        assert rc.rank_grade == "A_PLUS"
        assert rc.rank_score >= 85
        assert "Strong confluence" in " ".join(rc.reasons_for)

    def test_rank_a_candidate(self):
        ranker = CandidateRanker()
        cand = DummyCandidate()
        conf = DummyConfluence(score=75, confidence=0.7, conflict=0.15, reversal=30, continuation=55,
                                reasons_for=["sweep detected"])
        rc = ranker.rank(cand, conf)
        assert rc.rank_grade == "A"
        assert 70 <= rc.rank_score < 85

    def test_rank_b_candidate(self):
        ranker = CandidateRanker()
        cand = DummyCandidate()
        conf = DummyConfluence(score=55, confidence=0.5, conflict=0.4, reversal=45, continuation=40)
        rc = ranker.rank(cand, conf)
        assert rc.rank_grade == "B"
        assert 55 <= rc.rank_score < 70

    def test_rank_c_candidate(self):
        ranker = CandidateRanker()
        cand = DummyCandidate()
        conf = DummyConfluence(score=45, confidence=0.4, conflict=0.5, reversal=55, continuation=30)
        rc = ranker.rank(cand, conf)
        assert rc.rank_grade == "C"
        assert 40 <= rc.rank_score < 55

    def test_rank_reject_no_confluence(self):
        ranker = CandidateRanker()
        cand = DummyCandidate()
        rc = ranker.rank(cand, None)
        assert rc.rank_grade == "REJECT"
        assert "No confluence result" in rc.reasons_against

    def test_rank_reject_low_score(self):
        ranker = CandidateRanker()
        cand = DummyCandidate()
        conf = DummyConfluence(score=10, confidence=0.1, conflict=0.8, reversal=80, continuation=10)
        rc = ranker.rank(cand, conf)
        assert rc.rank_grade == "REJECT"
        assert rc.rank_score < 40

    def test_grades_exhaustive(self):
        ranker = CandidateRanker()
        assert set(RANK_GRADES) == {"A_PLUS", "A", "B", "C", "REJECT"}

    def test_target_realism_scoring(self):
        ranker = CandidateRanker()
        high = ranker._score_target_realism(3.0, 60)
        low = ranker._score_target_realism(1.0, 10)
        assert high > low
        assert 0 <= high <= 100
        assert 0 <= low <= 100

    def test_stop_quality_scoring(self):
        ranker = CandidateRanker()
        good = ranker._score_stop_quality(0.1, 10)
        bad = ranker._score_stop_quality(0.7, 70)
        assert good > bad

    def test_volatility_alignment(self):
        ranker = CandidateRanker()
        high = ranker._score_volatility_alignment(70, 20)
        low = ranker._score_volatility_alignment(30, 60)
        assert high > low

    def test_sweep_quality_no_sweep(self):
        ranker = CandidateRanker()
        conf = DummyConfluence()
        assert ranker._score_sweep_quality(conf) == 0.0

    def test_sweep_quality_with_sweep(self):
        ranker = CandidateRanker()
        conf = DummyConfluence(reasons_for=["liquidity sweep detected", "order flow above vwap"])
        score = ranker._score_sweep_quality(conf)
        assert score >= 25

    def test_orderflow_confirmation(self):
        ranker = CandidateRanker()
        conf = DummyConfluence(reasons_for=["order flow signals bullish"])
        assert ranker._score_orderflow(conf) == 80.0

    def test_orderflow_fallback(self):
        ranker = CandidateRanker()
        conf = DummyConfluence(reasons_for=["microstructure showing absorption"])
        assert ranker._score_orderflow(conf) == 50.0

    def test_rr_bonus_in_score(self):
        ranker = CandidateRanker()
        high_rr = DummyCandidate(target=55000, entry=50000, stop=49000)  # 5:1
        conf = DummyConfluence(score=60, confidence=0.6, conflict=0.3, reversal=40, continuation=50)
        rc_high = ranker.rank(high_rr, conf)
        low_rr = DummyCandidate(target=50500, entry=50000, stop=49000)  # 0.5:1
        rc_low = ranker.rank(low_rr, conf)
        assert rc_high.rank_score > rc_low.rank_score

    def test_ranked_candidate_has_all_fields(self):
        ranker = CandidateRanker()
        cand = DummyCandidate()
        conf = DummyConfluence()
        rc = ranker.rank(cand, conf)
        assert rc.candidate_id == "dummy_1"
        assert rc.symbol == "BTCUSDT"
        assert rc.direction == "LONG"
        assert rc.rr_ratio > 0
        assert rc.risk_score >= 0
        assert rc.expected_value_r is not None
