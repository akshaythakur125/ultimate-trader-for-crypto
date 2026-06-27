from typing import Any

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class FilterContributionResult:
    def __init__(self):
        self.filter_win_rate: dict[str, float] = {}
        self.filter_loss_rate: dict[str, float] = {}
        self.filter_avg_r: dict[str, float] = {}
        self.filter_trade_count: dict[str, int] = {}
        self.filters_helping: list[str] = []
        self.filters_hurting: list[str] = []
        self.filters_with_no_effect: list[str] = []
        self.filters_that_should_be_hardened: list[str] = []
        self.filters_that_should_be_removed_or_reweighted: list[str] = []


class FilterContributionAnalyzer:
    def analyze(self, trades: list[TradeDiagnostics]) -> FilterContributionResult:
        result = FilterContributionResult()

        all_filter_names = set()
        for t in trades:
            for f in t.filters_passed:
                all_filter_names.add(f)
            for f in t.filters_failed:
                all_filter_names.add(f)

        for filter_name in sorted(all_filter_names):
            trades_with_filter = [t for t in trades if filter_name in t.filters_passed or filter_name in t.filters_failed]
            passed_trades = [t for t in trades if filter_name in t.filters_passed]
            failed_trades = [t for t in trades if filter_name in t.filters_failed]

            if not trades_with_filter:
                continue

            passed_wins = sum(1 for t in passed_trades if t.is_winner())
            failed_wins = sum(1 for t in failed_trades if t.is_winner())
            passed_avg_r = sum(t.net_r for t in passed_trades) / len(passed_trades) if passed_trades else 0
            failed_avg_r = sum(t.net_r for t in failed_trades) / len(failed_trades) if failed_trades else 0

            result.filter_trade_count[filter_name] = len(trades_with_filter)
            result.filter_win_rate[filter_name] = (passed_wins / len(passed_trades) * 100) if passed_trades else 0.0
            result.filter_loss_rate[filter_name] = (failed_wins / len(failed_trades) * 100) if failed_trades else 0.0
            result.filter_avg_r[filter_name] = passed_avg_r

            if passed_trades and failed_trades:
                diff = passed_avg_r - failed_avg_r
                if diff > 0.1:
                    result.filters_helping.append(filter_name)
                elif diff < -0.1:
                    result.filters_hurting.append(filter_name)
                else:
                    result.filters_with_no_effect.append(filter_name)
            elif passed_trades and not failed_trades:
                result.filters_helping.append(filter_name)

        result.filters_that_should_be_hardened = [
            f for f in result.filters_hurting
            if result.filter_win_rate.get(f, 0) < 50
        ]
        result.filters_that_should_be_removed_or_reweighted = [
            f for f in result.filters_with_no_effect
            if result.filter_trade_count.get(f, 0) > 10
        ]

        return result
