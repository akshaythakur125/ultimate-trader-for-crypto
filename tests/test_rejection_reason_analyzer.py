import pytest
from ultimate_trader.selectivity_engine.rejection_reason_analyzer import RejectionReasonAnalyzer


class TestRejectionReasonAnalyzer:
    def test_records_low_rank(self):
        a = RejectionReasonAnalyzer()
        a.record("t1", "low_rank", "Grade B not allowed")
        assert a.stats.low_rank == 1
        assert len(a.reasons) == 1

    def test_records_confluence(self):
        a = RejectionReasonAnalyzer()
        a.record("t2", "confluence", "Score 30 < 50")
        assert a.stats.confluence == 1

    def test_records_confidence(self):
        a = RejectionReasonAnalyzer()
        a.record("t3", "directional_confidence", "Confidence 0.4 < 0.55")
        assert a.stats.directional_confidence == 1

    def test_records_conflict(self):
        a = RejectionReasonAnalyzer()
        a.record("t4", "conflict", "Conflict 0.6 > 0.4")
        assert a.stats.conflict == 1

    def test_records_reversal_risk(self):
        a = RejectionReasonAnalyzer()
        a.record("t5", "reversal_risk", "Reversal risk 55 > 50")
        assert a.stats.reversal_risk == 1

    def test_records_risk(self):
        a = RejectionReasonAnalyzer()
        a.record("t6", "risk", "Risk score 45 > 40")
        assert a.stats.risk == 1

    def test_records_rr(self):
        a = RejectionReasonAnalyzer()
        a.record("t7", "rr", "RR 2.0 < 3.0")
        assert a.stats.rr == 1

    def test_records_overtrading(self):
        a = RejectionReasonAnalyzer()
        a.record("t8", "overtrading", "Daily hard max reached")
        assert a.stats.overtrading == 1

    def test_records_cooldown(self):
        a = RejectionReasonAnalyzer()
        a.record("t9", "cooldown", "Same direction cooldown")
        assert a.stats.cooldown == 1

    def test_records_uncertainty(self):
        a = RejectionReasonAnalyzer()
        a.record("t10", "uncertainty", "Uncertain signal")
        assert a.stats.uncertainty == 1

    def test_multiple_records(self):
        a = RejectionReasonAnalyzer()
        for _ in range(3):
            a.record("t", "low_rank", "reason")
        for _ in range(2):
            a.record("t", "confluence", "reason")
        assert a.stats.low_rank == 3
        assert a.stats.confluence == 2
        assert len(a.reasons) == 5

    def test_reset(self):
        a = RejectionReasonAnalyzer()
        a.record("t1", "rr", "Low RR")
        a.record("t2", "conflict", "High conflict")
        a.reset()
        assert a.stats.low_rank == 0
        assert a.stats.rr == 0
        assert a.stats.conflict == 0
        assert len(a.reasons) == 0

    def test_unknown_category(self):
        a = RejectionReasonAnalyzer()
        a.record("t1", "unknown_category", "Something")
        assert a.stats.low_rank == 0
        assert a.stats.conflict == 0

    def test_reasons_list_format(self):
        a = RejectionReasonAnalyzer()
        a.record("t1", "rr", "Low RR 2.0")
        entry = a.reasons[0]
        assert len(entry) == 3
        assert entry[0] == "t1"
        assert entry[1] == "rr"
        assert entry[2] == "Low RR 2.0"
