from typing import Optional

from ultimate_trader.drawdown_control.equity_curve import DrawdownEpisode, EquityCurve
from ultimate_trader.historical_replay.models import ReplayTrade


class DrawdownAnalyzer:
    def analyze(self, trades: list[ReplayTrade]) -> dict:
        ec = EquityCurve(trades)
        episodes = ec.episodes
        worst_ep = max(episodes, key=lambda e: e.depth_r) if episodes else None

        n_large = 0
        n_small = 0
        for e in episodes:
            if e.cause == "few_large_losses":
                n_large += 1
            else:
                n_small += 1

        return {
            "total_drawdown_episodes": len(episodes),
            "max_drawdown_r": ec.max_drawdown_r,
            "max_drawdown_start": ec.max_drawdown_start,
            "max_drawdown_end": ec.max_drawdown_end,
            "episodes_large_loss": n_large,
            "episodes_small_loss": n_small,
            "largest_episode": self._episode_summary(worst_ep) if worst_ep else None,
            "worst_5_drops": ec.worst_5_drops,
            "underwater_periods": ec.underwater_periods,
        }

    def _episode_summary(self, ep: DrawdownEpisode) -> dict:
        return {
            "start": ep.start.strftime("%Y-%m-%d %H:%M") if ep.start else "",
            "end": ep.end.strftime("%Y-%m-%d %H:%M") if ep.end else "ongoing",
            "depth_r": round(ep.depth_r, 2),
            "num_trades": ep.num_trades,
            "symbols": list(set(ep.symbols)),
            "win_rate": round(ep.win_rate, 3),
            "avg_r": round(ep.avg_r, 3),
            "cause": ep.cause,
            "top_losing_trades": ep.top_losing_trades[:3],
        }
