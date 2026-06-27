from pydantic import BaseModel, Field

from ultimate_trader.historical_replay.models import ReplayTrade


class ReplayMetrics(BaseModel):
    total_signals: int = 0
    rejected_signals: int = 0
    executed_trades: int = 0
    win_rate: float = 0.0
    average_r: float = 0.0
    expectancy_r: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_r: float = 0.0
    max_consecutive_losses: int = 0
    average_holding_time: float = 0.0
    best_trade_r: float = 0.0
    worst_trade_r: float = 0.0
    rejection_rate: float = 0.0
    signal_to_trade_conversion_rate: float = 0.0

    @classmethod
    def calculate(
        cls,
        trades: list[ReplayTrade],
        total_signals: int,
        rejected_signals: int,
    ) -> "ReplayMetrics":
        executed = len(trades)
        if executed == 0:
            return cls(
                total_signals=total_signals,
                rejected_signals=rejected_signals,
                executed_trades=0,
                rejection_rate=rejected_signals / total_signals if total_signals > 0 else 0.0,
                signal_to_trade_conversion_rate=0.0,
            )

        wins = [t for t in trades if t.net_r > 0]
        losses = [t for t in trades if t.net_r <= 0]
        win_rate = len(wins) / executed

        total_net_r = sum(t.net_r for t in trades)
        average_r = total_net_r / executed

        total_win_r = sum(t.net_r for t in wins) if wins else 0.0
        total_loss_r = abs(sum(t.net_r for t in losses)) if losses else 0.0
        profit_factor = total_win_r / total_loss_r if total_loss_r > 0 else (total_win_r if total_win_r > 0 else 0.0)

        expectancy_r = average_r

        best_trade_r = max(t.net_r for t in trades)
        worst_trade_r = min(t.net_r for t in trades)

        avg_holding = sum(t.holding_candles for t in trades) / executed

        peak = 0.0
        drawdown = 0.0
        running = 0.0
        for t in trades:
            running += t.net_r
            if running > peak:
                peak = running
            dd = peak - running
            if dd > drawdown:
                drawdown = dd
        max_drawdown_r = drawdown

        max_consecutive_losses = 0
        current_streak = 0
        for t in trades:
            if t.net_r <= 0:
                current_streak += 1
                if current_streak > max_consecutive_losses:
                    max_consecutive_losses = current_streak
            else:
                current_streak = 0

        rejection_rate = rejected_signals / total_signals if total_signals > 0 else 0.0
        conversion = executed / (total_signals - rejected_signals) if (total_signals - rejected_signals) > 0 else 0.0

        return cls(
            total_signals=total_signals,
            rejected_signals=rejected_signals,
            executed_trades=executed,
            win_rate=round(win_rate, 4),
            average_r=round(average_r, 4),
            expectancy_r=round(expectancy_r, 4),
            profit_factor=round(profit_factor, 4),
            max_drawdown_r=round(max_drawdown_r, 4),
            max_consecutive_losses=max_consecutive_losses,
            average_holding_time=round(avg_holding, 2),
            best_trade_r=round(best_trade_r, 4),
            worst_trade_r=round(worst_trade_r, 4),
            rejection_rate=round(rejection_rate, 4),
            signal_to_trade_conversion_rate=round(conversion, 4),
        )
