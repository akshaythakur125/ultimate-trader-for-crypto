from collections import defaultdict
from datetime import datetime
from typing import Any

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class OvertradingResult:
    def __init__(self):
        self.total_trades: int = 0
        self.unique_days: int = 0
        self.trades_per_day: dict[str, int] = {}
        self.max_trades_in_day: int = 0
        self.avg_trades_per_day: float = 0.0
        self.repeated_direction_trades: int = 0
        self.signal_clusters: list[list[str]] = []
        self.overtrading_warning: bool = False
        self.severe_overtrading_warning: bool = False
        self.days_above_4: int = 0
        self.days_above_10: int = 0
        self.summary: str = ""


class OvertradingDetector:
    def analyze(self, trades: list[TradeDiagnostics]) -> OvertradingResult:
        result = OvertradingResult()
        result.total_trades = len(trades)

        if not trades:
            result.summary = "No trades to analyze"
            return result

        daily: dict[str, list[TradeDiagnostics]] = defaultdict(list)
        for t in trades:
            day_key = t.signal_time.strftime("%Y-%m-%d")
            daily[day_key].append(t)

        result.unique_days = len(daily)
        result.trades_per_day = {day: len(tlist) for day, tlist in daily.items()}
        result.max_trades_in_day = max(result.trades_per_day.values()) if result.trades_per_day else 0
        result.avg_trades_per_day = result.total_trades / result.unique_days if result.unique_days > 0 else 0.0

        result.days_above_4 = sum(1 for v in result.trades_per_day.values() if v > 4)
        result.days_above_10 = sum(1 for v in result.trades_per_day.values() if v > 10)

        if result.max_trades_in_day > 10 or result.days_above_10 > 0:
            result.severe_overtrading_warning = True
            result.overtrading_warning = True
        elif result.max_trades_in_day > 4 or result.avg_trades_per_day > 4:
            result.overtrading_warning = True

        repeated = 0
        prev_dir = None
        prev_symbol = None
        for t in trades:
            if prev_dir is not None and prev_symbol is not None:
                if t.direction.value == prev_dir and t.symbol == prev_symbol:
                    repeated += 1
            prev_dir = t.direction.value
            prev_symbol = t.symbol
        result.repeated_direction_trades = repeated

        cluster: list[str] = []
        for day in sorted(daily.keys()):
            day_trades = daily[day]
            if len(day_trades) >= 3:
                cluster.append(f"{day}: {len(day_trades)} trades")
        result.signal_clusters = cluster

        parts = []
        if result.severe_overtrading_warning:
            parts.append(f"SEVERE overtrading: max {result.max_trades_in_day} trades in one day (target: 2-4/day)")
        elif result.overtrading_warning:
            parts.append(f"Overtrading detected: avg {result.avg_trades_per_day:.1f} trades/day, max {result.max_trades_in_day}")
        else:
            parts.append(f"Trading frequency acceptable: avg {result.avg_trades_per_day:.1f} trades/day")

        if result.days_above_4 > 0:
            parts.append(f"{result.days_above_4} day(s) exceeded 4 trades")
        if result.days_above_10 > 0:
            parts.append(f"{result.days_above_10} day(s) exceeded 10 trades")
        if result.repeated_direction_trades > result.total_trades * 0.5:
            parts.append(f"High same-direction repetition: {result.repeated_direction_trades}/{result.total_trades} consecutive same-dir trades")

        result.summary = " | ".join(parts)
        return result
