from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection


class LossClusterAnalyzer:
    def analyze(self, trades: list[ReplayTrade]) -> dict:
        sorted_trades = sorted(trades, key=lambda t: t.signal_time)

        consecutive_losses = 0
        max_consecutive_losses = 0
        current_cluster_trades: list[ReplayTrade] = []
        clusters: list[dict] = []

        daily_losses: defaultdict[str, float] = defaultdict(float)
        daily_loss_counts: defaultdict[str, int] = defaultdict(int)
        symbol_losses: defaultdict[str, list] = defaultdict(list)
        direction_streak = 0
        last_direction: Optional[TradeDirection] = None
        same_direction_losses = 0

        for t in sorted_trades:
            if t.net_r <= 0:
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                current_cluster_trades.append(t)
                day_key = t.signal_time.strftime("%Y-%m-%d")
                daily_losses[day_key] += t.net_r
                daily_loss_counts[day_key] += 1
                symbol_losses[t.symbol].append(t)

                if last_direction == t.direction:
                    same_direction_losses += 1
                else:
                    same_direction_losses = 1
                last_direction = t.direction
                direction_streak += 1 if last_direction != t.direction else 1

                if len(current_cluster_trades) >= 3:
                    self._close_cluster(clusters, current_cluster_trades)
                    current_cluster_trades = []
            else:
                if clen := len(current_cluster_trades) >= 2:
                    self._close_cluster(clusters, current_cluster_trades)
                current_cluster_trades = []
                consecutive_losses = 0
                same_direction_losses = 0

        if len(current_cluster_trades) >= 2:
            self._close_cluster(clusters, current_cluster_trades)

        symbol_loss_summary = {}
        for sym, ltrades in symbol_losses.items():
            total_loss = abs(sum(t.net_r for t in ltrades))
            symbol_loss_summary[sym] = {
                "loss_trades": len(ltrades),
                "total_loss_r": round(total_loss, 2),
                "avg_loss_r": round(total_loss / len(ltrades), 2) if ltrades else 0,
            }

        worst_day = min(daily_losses.items(), key=lambda x: x[1]) if daily_losses else ("", 0)

        return {
            "max_consecutive_losses": max_consecutive_losses,
            "total_loss_clusters": len(clusters),
            "severe_clusters": [c for c in clusters if c["total_loss_r"] >= 2.0],
            "daily_loss_summary": {
                "worst_day": worst_day[0] if worst_day[0] else "",
                "worst_day_loss_r": round(worst_day[1], 2) if worst_day[1] else 0,
                "days_with_losses": len(daily_losses),
            },
            "symbol_loss_summary": symbol_loss_summary,
            "max_same_direction_losses": same_direction_losses,
            "clusters": clusters[:10],
        }

    def _close_cluster(self, clusters: list, ctrades: list[ReplayTrade]):
        syms = list(set(t.symbol for t in ctrades))
        total_loss = sum(t.net_r for t in ctrades)
        wins_in_cluster = [t for t in ctrades if t.net_r > 0]
        loses_in_cluster = [t for t in ctrades if t.net_r <= 0]
        clusters.append({
            "start": ctrades[0].signal_time.strftime("%Y-%m-%d %H:%M"),
            "end": ctrades[-1].signal_time.strftime("%Y-%m-%d %H:%M"),
            "num_trades": len(ctrades),
            "total_loss_r": round(abs(total_loss), 2),
            "win_rate": len(wins_in_cluster) / len(ctrades) if ctrades else 0,
            "symbols": syms,
            "avg_loss_r": round(abs(total_loss) / len(loses_in_cluster), 2) if loses_in_cluster else 0,
        })
