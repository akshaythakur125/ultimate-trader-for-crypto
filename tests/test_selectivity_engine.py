import pytest
from datetime import datetime
from ultimate_trader.selectivity_engine import (
    CandidateRanker, QualityGate, DailySelector,
    RejectionReasonAnalyzer, SelectivityReport,
)
from ultimate_trader.selectivity_engine.quality_gate import QualityGateConfig
from ultimate_trader.selectivity_engine.daily_selector import DailySelectorConfig


class TestSelectivityPipeline:
    def test_full_pipeline_selects_best(self):
        ranker = CandidateRanker()
        gate = QualityGate()
        selector = DailySelector(gate)
        analyzer = RejectionReasonAnalyzer()

        candidates = []
        for i, (score, grade, dir) in enumerate([
            (50, "C", "LONG"),
            (75, "A", "SHORT"),
            (90, "A_PLUS", "LONG"),
            (40, "REJECT", "SHORT"),
        ]):
            from ultimate_trader.selectivity_engine.candidate_ranker import RankedCandidate
            rc = RankedCandidate(
                candidate_id=f"t{i}", symbol="BTCUSDT", direction=dir,
                timestamp=datetime(2025, 6, 1, 10 + i, 0),
                rank_grade=grade, rank_score=float(score),
                confluence_score=float(score), directional_confidence=score / 100,
                conflict_score=0.2, reversal_risk_score=30,
                risk_score=20, rr_ratio=3.0,
                continuation_score=50, target_realism_score=60,
                stop_quality_score=70, volatility_alignment=60,
            )
            candidates.append(rc)
            selector.register_candidate(rc)

            qr = gate.evaluate(rc)
            if not qr.passed:
                analyzer.record(rc.candidate_id, qr.rejection_category, qr.rejection_reason)

        results = selector.select_for_day("2025-06-01")
        allowed = [(rc, r) for rc, r in results if r.allowed]

        assert any(rc.candidate_id == "t2" for rc, r in allowed)
        assert all(rc.rank_grade == "A_PLUS" or rc.rank_grade == "A" for rc, r in allowed)

    def test_report_generation(self):
        baseline = {"total_trades": 100, "win_rate": 0.30, "expectancy": -0.15, "profit_factor": 0.85, "avg_trades_per_day": 25}
        selective = {"total_trades": 20, "win_rate": 0.45, "expectancy": 0.20, "profit_factor": 1.35, "avg_trades_per_day": 3}
        stats = type("Stats", (), {"low_rank": 10, "confluence": 5, "directional_confidence": 3, "conflict": 7, "reversal_risk": 2, "risk": 4, "rr": 6, "overtrading": 8, "cooldown": 3, "uncertainty": 0})()
        daily_breakdown = {"2025-06-01": 3, "2025-06-02": 2}

        report = SelectivityReport.generate(baseline, selective, stats, daily_breakdown)
        assert "EDGE DETECTED" in report
        assert "Selective trades:" in report
        assert "expectancy" in report.lower()
        assert "profit factor" in report.lower()

    def test_report_no_edge(self):
        baseline = {"total_trades": 100, "win_rate": 0.30, "expectancy": -0.15, "profit_factor": 0.85, "avg_trades_per_day": 25}
        selective = {"total_trades": 20, "win_rate": 0.30, "expectancy": -0.15, "profit_factor": 0.85, "avg_trades_per_day": 3}
        stats = type("Stats", (), {"low_rank": 10, "confluence": 5, "directional_confidence": 3, "conflict": 7, "reversal_risk": 2, "risk": 4, "rr": 6, "overtrading": 8, "cooldown": 3, "uncertainty": 0})()
        report = SelectivityReport.generate(baseline, selective, stats, {})
        assert "NO_EDGE" in report

    def test_pipeline_rejects_bad_candidates(self):
        ranker = CandidateRanker()
        gate = QualityGate()
        selector = DailySelector(gate)
        analyzer = RejectionReasonAnalyzer()

        from ultimate_trader.selectivity_engine.candidate_ranker import RankedCandidate
        rc = RankedCandidate(
            candidate_id="bad", symbol="BTCUSDT", direction="LONG",
            timestamp=datetime(2025, 6, 1, 10, 0),
            rank_grade="REJECT", rank_score=15.0,
            confluence_score=15.0, directional_confidence=0.15,
            conflict_score=0.8, reversal_risk_score=80,
            risk_score=70, rr_ratio=1.0,
            continuation_score=10, target_realism_score=10,
            stop_quality_score=10, volatility_alignment=10,
        )
        qr = gate.evaluate(rc)
        assert not qr.passed
        analyzer.record(rc.candidate_id, qr.rejection_category, qr.rejection_reason)
        assert analyzer.stats.low_rank == 1
