from collections import defaultdict
from typing import Any

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class DailyStats:
    def __init__(self, date_str: str = ""):
        self.date_str: str = date_str
        self.total: int = 0
        self.wins: int = 0
        self.losses: int = 0
        self.expectancy: float = 0.0
        self.total_r: float = 0.0


class DailyTradeDistribution:
    def analyze(self, trades: list[TradeDiagnostics]) -> dict[str, DailyStats]:
        daily: dict[str, list[TradeDiagnostics]] = defaultdict(list)
        for t in trades:
            day_key = t.signal_time.strftime("%Y-%m-%d")
            daily[day_key].append(t)

        result: dict[str, DailyStats] = {}
        for day, day_trades in sorted(daily.items()):
            ds = DailyStats(day)
            ds.total = len(day_trades)
            ds.wins = sum(1 for t in day_trades if t.is_winner())
            ds.losses = sum(1 for t in day_trades if t.is_loser())
            ds.total_r = sum(t.net_r for t in day_trades)
            ds.expectancy = ds.total_r / ds.total if ds.total > 0 else 0.0
            result[day] = ds

        return result
