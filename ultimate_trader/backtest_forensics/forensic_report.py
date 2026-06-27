from collections import Counter
from typing import Any

from ultimate_trader.backtest_forensics.failure_classifier import FailureCategory, FailureClassifier
from ultimate_trader.backtest_forensics.filter_contribution import FilterContributionAnalyzer
from ultimate_trader.backtest_forensics.outcome_analyzer import OutcomeAnalyzer
from ultimate_trader.backtest_forensics.overtrading_detector import OvertradingDetector
from ultimate_trader.backtest_forensics.stop_target_auditor import StopTargetAuditor
from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class ForensicReport:
    def __init__(self):
        self.total_trades_analyzed: int = 0
        self.win_rate: float = 0.0
        self.expectancy: float = 0.0
        self.top_5_failure_causes: list[str] = []
        self.stop_target_problems: list[str] = []
        self.entry_problems: list[str] = []
        self.overtrading_status: str = ""
        self.same_candle_stop_first_impact: str = ""
        self.filter_contribution_summary: str = ""
        self.recommended_next_fixes: list[str] = []
        self.results_reliable: bool = True
        self.simulator_bug_suspected: bool = False

    @classmethod
    def generate(cls, trades: list[TradeDiagnostics]) -> "ForensicReport":
        report = cls()
        report.total_trades_analyzed = len(trades)

        if not trades:
            report.results_reliable = False
            report.recommended_next_fixes = ["No trades to analyze"]
            return report

        outcome = OutcomeAnalyzer().analyze(trades)
        report.win_rate = outcome.win_rate
        report.expectancy = outcome.avg_r

        classifier = FailureClassifier()
        failure_counts: Counter[str] = Counter()
        for t in trades:
            if t.is_loser():
                fc = classifier.classify(t)
                failure_counts[fc.category.value] += 1

        total_losses = sum(1 for t in trades if t.is_loser())
        if total_losses > 0:
            report.top_5_failure_causes = [
                f"{cat} ({count}/{total_losses} losses, {count/total_losses*100:.0f}%)"
                for cat, count in failure_counts.most_common(5)
            ]
        else:
            report.top_5_failure_causes = ["No losing trades"]

        auditor = StopTargetAuditor()
        stop_target_problems_set: set[str] = set()
        for t in trades:
            audit = auditor.audit(t)
            if not audit.stop_target_valid:
                for w in audit.warnings:
                    stop_target_problems_set.add(w.split("—")[0].strip() if "—" in w else w)
        report.stop_target_problems = list(stop_target_problems_set)[:5]

        report.same_candle_stop_first_impact = (
            f"{outcome.same_candle_stop_first}/{outcome.total_trades} trades "
            f"({outcome.same_candle_stop_first_pct:.1f}%) stopped on same candle as entry"
        )
        if outcome.same_candle_stop_first_pct > 30:
            report.same_candle_stop_first_impact += " — CRITICAL: entry logic issue suspected"

        overtrading = OvertradingDetector().analyze(trades)
        report.overtrading_status = overtrading.summary

        filter_analyzer = FilterContributionAnalyzer()
        filter_result = filter_analyzer.analyze(trades)
        helping = filter_result.filters_helping
        hurting = filter_result.filters_hurting
        no_effect = filter_result.filters_that_should_be_removed_or_reweighted

        parts = []
        if helping:
            parts.append(f"Helping: {', '.join(helping)}")
        if hurting:
            parts.append(f"Hurting: {', '.join(hurting)}")
        if no_effect:
            parts.append(f"Remove/reweight: {', '.join(no_effect)}")
        report.filter_contribution_summary = " | ".join(parts) if parts else "Insufficient data"

        report.recommended_next_fixes = []
        if outcome.same_candle_stop_first_pct > 20:
            report.recommended_next_fixes.append(
                f"Fix same-candle stop-first ({outcome.same_candle_stop_first_pct:.0f}% of trades) — widen entry zone or use limit entry"
            )
        if overtrading.overtrading_warning:
            report.recommended_next_fixes.append(
                f"Reduce trade frequency ({overtrading.avg_trades_per_day:.1f}/day, max {overtrading.max_trades_in_day})"
            )
        if "STOP_TOO_TIGHT" in [c.split("(")[0].strip() for c in report.top_5_failure_causes]:
            report.recommended_next_fixes.append("Widen stop loss — current stop is inside normal noise")
        if "TARGET_TOO_AMBITIOUS" in [c.split("(")[0].strip() for c in report.top_5_failure_causes]:
            report.recommended_next_fixes.append("Reduce target distance or implement trailing stop")
        if "SAME_CANDLE_STOP_FIRST" in [c.split("(")[0].strip() for c in report.top_5_failure_causes]:
            report.recommended_next_fixes.append("Review same-candle stop-first logic — stop may trigger before fill")
        if "SIMULATOR_LOGIC_ISSUE" in [c.split("(")[0].strip() for c in report.top_5_failure_causes]:
            report.recommended_next_fixes.append("CRITICAL: Check simulator entry/stop fill order — bug suspected")
            report.simulator_bug_suspected = True
        if not report.recommended_next_fixes:
            report.recommended_next_fixes = ["Results appear realistic; further tuning optional"]

        if outcome.same_candle_stop_first_pct > 50 or overtrading.severe_overtrading_warning:
            report.results_reliable = False

        return report
