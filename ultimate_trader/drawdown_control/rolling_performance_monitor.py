from collections import defaultdict
from datetime import datetime
from typing import Optional

from ultimate_trader.historical_replay.models import ReplayTrade


class RollingPerformanceMonitor:
    def __init__(self, trades: list[ReplayTrade]):
        self._trades = sorted(trades, key=lambda t: t.signal_time)

    def rolling_expectancy(self, n: int = 10) -> list[dict]:
        return self._rolling(trades=self._trades, n=n, metric="ev")

    def rolling_profit_factor(self, n: int = 20) -> list[dict]:
        return self._rolling(trades=self._trades, n=n, metric="pf")

    def rolling_win_rate(self, n: int = 10) -> list[dict]:
        return self._rolling(trades=self._trades, n=n, metric="wr")

    def rolling_drawdown(self) -> list[dict]:
        result = []
        cum = 0.0
        peak = 0.0
        for t in self._trades:
            cum += t.net_r
            peak = max(peak, cum)
            dd = peak - cum
            result.append({
                "timestamp": t.signal_time.strftime("%Y-%m-%d %H:%M"),
                "drawdown_r": round(dd, 2),
            })
        return result

    def symbol_rolling(self, symbol: str, n: int = 10) -> list[dict]:
        sym_trades = [t for t in self._trades if t.symbol == symbol]
        return self._rolling(trades=sym_trades, n=n, metric="ev")

    def latest(self) -> dict:
        if len(self._trades) < 10:
            return {"rolling_10_ev": 0, "rolling_20_pf": 0, "rolling_10_wr": 0, "sufficient_data": False}
        last10 = self._trades[-10:]
        last20 = self._trades[-20:] if len(self._trades) >= 20 else self._trades
        wins10 = [t for t in last10 if t.net_r > 0]
        wins20 = [t for t in last20 if t.net_r > 0]
        losses20 = [t for t in last20 if t.net_r <= 0]
        gp20 = sum(t.net_r for t in wins20)
        gl20 = abs(sum(t.net_r for t in losses20))
        return {
            "rolling_10_ev": round(sum(t.net_r for t in last10) / len(last10), 3),
            "rolling_20_pf": round(gp20 / gl20, 2) if gl20 > 0 else 99.0,
            "rolling_10_wr": round(len(wins10) / len(last10), 3),
            "sufficient_data": True,
            "total_trades": len(self._trades),
        }

    def _rolling(self, trades: list, n: int, metric: str) -> list[dict]:
        result = []
        for i in range(n - 1, len(trades)):
            window = trades[i - n + 1:i + 1]
            if metric == "ev":
                val = sum(t.net_r for t in window) / n
            elif metric == "pf":
                wins = [t for t in window if t.net_r > 0]
                losses = [t for t in window if t.net_r <= 0]
                gp = sum(t.net_r for t in wins)
                gl = abs(sum(t.net_r for t in losses))
                val = gp / gl if gl > 0 else 99.0
            elif metric == "wr":
                wins = [t for t in window if t.net_r > 0]
                val = len(wins) / n
            else:
                val = 0.0
            result.append({
                "timestamp": trades[i].signal_time.strftime("%Y-%m-%d %H:%M"),
                "value": round(val, 3),
            })
        return result
