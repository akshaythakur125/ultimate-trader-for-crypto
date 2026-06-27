from dataclasses import dataclass, field
from typing import Optional

from ultimate_trader.historical_replay.models import ReplayTrade


RELIABILITY_STATUSES = ["RELIABLE", "PROMISING", "UNSTABLE", "DANGEROUS", "INSUFFICIENT_TRADES"]


@dataclass
class SymbolTimeframeResult:
    symbol: str
    timeframe: str
    trades: int
    win_rate: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    total_profit_r: float
    contribution_to_profit: float = 0.0
    contribution_to_drawdown: float = 0.0
    reliability: str = "INSUFFICIENT_TRADES"


class SymbolTimeframeAttribution:
    def analyze(
        self,
        grouped_results: dict[tuple[str, str], list[ReplayTrade]],
        total_net_r: float = 0.0,
        total_max_dd: float = 0.0,
    ) -> list[SymbolTimeframeResult]:
        results: list[SymbolTimeframeResult] = []

        for (symbol, timeframe), trades in grouped_results.items():
            if not trades:
                continue
            wins = [t for t in trades if t.net_r > 0]
            losses = [t for t in trades if t.net_r <= 0]
            total_r = sum(t.net_r for t in trades)
            gp = sum(t.net_r for t in wins)
            gl = abs(sum(t.net_r for t in losses))
            pf = gp / gl if gl > 0 else 99.0
            wr = len(wins) / len(trades) if trades else 0
            ev = total_r / len(trades) if trades else 0

            eq = [0]
            for t in sorted(trades, key=lambda x: x.signal_time):
                eq.append(eq[-1] + t.net_r)
            dd = 0
            peak = eq[0]
            for v in eq:
                if v > peak:
                    peak = v
                dd = max(dd, peak - v)

            st = SymbolTimeframeResult(
                symbol=symbol, timeframe=timeframe,
                trades=len(trades), win_rate=round(wr, 3),
                expectancy=round(ev, 3), profit_factor=round(pf, 3),
                max_drawdown=round(dd, 2),
                total_profit_r=round(total_r, 2),
            )

            if total_net_r != 0:
                st.contribution_to_profit = round(total_r / total_net_r * 100, 1)
            if total_max_dd != 0:
                st.contribution_to_drawdown = round(dd / total_max_dd * 100, 1)

            if len(trades) < 5:
                st.reliability = "INSUFFICIENT_TRADES"
            elif wr >= 0.45 and ev > 0.3 and pf > 1.5 and dd < 5.0:
                st.reliability = "RELIABLE"
            elif wr >= 0.40 and ev > 0.1 and pf > 1.2:
                st.reliability = "PROMISING"
            elif ev > 0:
                st.reliability = "UNSTABLE"
            else:
                st.reliability = "DANGEROUS"

            results.append(st)

        results.sort(key=lambda r: r.contribution_to_profit, reverse=True)
        return results
