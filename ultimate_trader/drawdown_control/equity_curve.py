from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ultimate_trader.historical_replay.models import ReplayTrade


@dataclass
class DrawdownEpisode:
    start: datetime
    end: Optional[datetime] = None
    depth_r: float = 0.0
    peak_r: float = 0.0
    trough_r: float = 0.0
    num_trades: int = 0
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
    win_rate: float = 0.0
    avg_r: float = 0.0
    top_losing_trades: list[dict] = field(default_factory=list)
    cause: str = ""


@dataclass
class EquityPoint:
    timestamp: datetime
    cumulative_r: float
    peak_r: float
    drawdown_r: float
    trade: Optional[ReplayTrade] = None


class EquityCurve:
    def __init__(self, trades: list[ReplayTrade]):
        self._trades = sorted(trades, key=lambda t: t.signal_time)
        self._points: list[EquityPoint] = []
        self._episodes: list[DrawdownEpisode] = []
        self._build()

    @property
    def points(self) -> list[EquityPoint]:
        return list(self._points)

    @property
    def episodes(self) -> list[DrawdownEpisode]:
        return list(self._episodes)

    @property
    def total_r(self) -> float:
        return self._points[-1].cumulative_r if self._points else 0.0

    @property
    def max_drawdown_r(self) -> float:
        return max((p.drawdown_r for p in self._points), default=0.0)

    @property
    def max_drawdown_start(self) -> Optional[datetime]:
        if not self._episodes:
            return None
        return max(self._episodes, key=lambda e: e.depth_r).start

    @property
    def max_drawdown_end(self) -> Optional[datetime]:
        if not self._episodes:
            return None
        return max(self._episodes, key=lambda e: e.depth_r).end

    @property
    def worst_5_drops(self) -> list[dict]:
        drops = sorted(self._episodes, key=lambda e: e.depth_r, reverse=True)
        return [
            {"start": e.start.strftime("%Y-%m-%d %H:%M"),
             "end": e.end.strftime("%Y-%m-%d %H:%M") if e.end else "ongoing",
             "depth_r": e.depth_r, "cause": e.cause}
            for e in drops[:5]
        ]

    @property
    def underwater_periods(self) -> list[dict]:
        under = []
        for e in self._episodes:
            if e.depth_r > 0:
                under.append({"start": e.start.strftime("%Y-%m-%d %H:%M"),
                              "end": e.end.strftime("%Y-%m-%d %H:%M") if e.end else "ongoing",
                              "depth_r": e.depth_r})
        return under

    def recovery_time(self, episode: DrawdownEpisode) -> Optional[int]:
        if not episode.end:
            return None
        start_idx = next((i for i, p in enumerate(self._points)
                          if p.timestamp >= episode.start), None)
        end_idx = next((i for i, p in enumerate(self._points)
                        if p.timestamp >= episode.end), None)
        if start_idx is None or end_idx is None:
            return None
        return end_idx - start_idx

    def _build(self):
        cum = 0.0
        peak = 0.0
        dd_active = False
        current_ep: Optional[DrawdownEpisode] = None

        for t in self._trades:
            cum += t.net_r
            prev_peak = peak
            peak = max(peak, cum)
            dd = max(0, peak - cum)
            self._points.append(EquityPoint(
                timestamp=t.signal_time, cumulative_r=cum,
                peak_r=peak, drawdown_r=dd, trade=t,
            ))

            if dd > 0:
                if not dd_active:
                    dd_active = True
                    current_ep = DrawdownEpisode(
                        start=t.signal_time, peak_r=peak, trough_r=cum,
                    )
                if current_ep is not None:
                    if cum < current_ep.trough_r:
                        current_ep.trough_r = cum
                        current_ep.depth_r = current_ep.peak_r - cum
                    current_ep.num_trades += 1
                    if t.symbol and t.symbol not in current_ep.symbols:
                        current_ep.symbols.append(t.symbol)
                    if t.net_r < 0 and t.net_r <= -0.5:
                        current_ep.top_losing_trades.append({
                            "trade_id": t.trade_id, "symbol": t.symbol,
                            "net_r": round(t.net_r, 2),
                            "time": t.signal_time.strftime("%Y-%m-%d %H:%M"),
                        })
            else:
                if dd_active and current_ep is not None:
                    current_ep.end = t.signal_time
                    current_ep.depth_r = current_ep.peak_r - current_ep.trough_r
                    if current_ep.num_trades > 0:
                        ep_trades = [tt for tt in self._trades
                                     if current_ep.start <= tt.signal_time <= (current_ep.end or tt.signal_time)]
                        wins = [tt for tt in ep_trades if tt.net_r > 0]
                        current_ep.win_rate = len(wins) / len(ep_trades) if ep_trades else 0
                        current_ep.avg_r = sum(tt.net_r for tt in ep_trades) / len(ep_trades) if ep_trades else 0
                    current_ep.top_losing_trades.sort(key=lambda x: x["net_r"])
                    current_ep.top_losing_trades = current_ep.top_losing_trades[:5]
                    if current_ep.top_losing_trades:
                        n_large = sum(1 for x in current_ep.top_losing_trades if x["net_r"] <= -1.0)
                        current_ep.cause = "few_large_losses" if n_large >= 2 else "many_small_losses"
                    else:
                        current_ep.cause = "many_small_losses"
                    self._episodes.append(current_ep)
                dd_active = False
                current_ep = None

        if dd_active and current_ep is not None:
            current_ep.end = self._trades[-1].exit_time or self._trades[-1].signal_time
            current_ep.depth_r = current_ep.peak_r - current_ep.trough_r
            if current_ep.num_trades > 0:
                ep_trades = [tt for tt in self._trades
                             if current_ep.start <= tt.signal_time <= (current_ep.end or tt.signal_time)]
                wins = [tt for tt in ep_trades if tt.net_r > 0]
                current_ep.win_rate = len(wins) / len(ep_trades) if ep_trades else 0
                current_ep.avg_r = sum(tt.net_r for tt in ep_trades) / len(ep_trades) if ep_trades else 0
            self._episodes.append(current_ep)
