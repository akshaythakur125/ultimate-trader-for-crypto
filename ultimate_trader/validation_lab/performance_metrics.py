from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    MANUAL = "MANUAL"
    TIME_EXIT = "TIME_EXIT"
    SIGNAL_CLOSE = "SIGNAL_CLOSE"


class TradeResult(BaseModel):
    trade_id: str
    hypothesis_id: str
    symbol: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    direction: Direction
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    gross_r: float = 0.0
    fees_r: float = 0.0
    slippage_r: float = 0.0
    funding_r: float = 0.0
    net_r: float = 0.0
    max_favorable_excursion_r: Optional[float] = None
    max_adverse_excursion_r: Optional[float] = None
    exit_reason: Optional[ExitReason] = None


class PerformanceMetrics(BaseModel):
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    average_win_r: float = 0.0
    average_loss_r: float = 0.0
    average_rr: float = 0.0
    expectancy_r: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_r: float = 0.0
    max_drawdown_percent: float = 0.0
    max_daily_drawdown_percent: float = 0.0
    sharpe_like_ratio: float = 0.0
    consecutive_losses_max: int = 0
    false_signal_rate: float = 0.0
    average_holding_time_hours: float = 0.0

    @staticmethod
    def calculate(trades: list[TradeResult]) -> "PerformanceMetrics":
        total = len(trades)
        if total == 0:
            return PerformanceMetrics()

        wins = [t for t in trades if t.net_r > 0]
        losses = [t for t in trades if t.net_r <= 0]
        num_wins = len(wins)
        num_losses = len(losses)

        win_rate = num_wins / total if total > 0 else 0.0
        avg_win = sum(t.net_r for t in wins) / num_wins if num_wins > 0 else 0.0
        avg_loss = sum(t.net_r for t in losses) / num_losses if num_losses > 0 else 0.0

        gross_profit = sum(t.net_r for t in wins)
        gross_loss = abs(sum(t.net_r for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        avg_rr = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        returns = [t.net_r for t in trades]
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in returns:
            cumulative += r
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)

        max_dd_pct = (max_dd / peak * 100) if peak > 0 else 0.0

        avg_r = sum(returns) / total if total > 0 else 0.0
        std_r = (sum((r - avg_r) ** 2 for r in returns) / total) ** 0.5 if total > 0 else 0.0
        sharpe = avg_r / std_r if std_r > 0 else 0.0

        max_consecutive = 0
        current = 0
        for t in trades:
            if t.net_r <= 0:
                current += 1
                max_consecutive = max(max_consecutive, current)
            else:
                current = 0

        false_signals = len([t for t in trades if t.net_r < -2.0])
        false_signal_rate = false_signals / total if total > 0 else 0.0

        holding_times = []
        for t in trades:
            if t.entry_time and t.exit_time:
                delta = (t.exit_time - t.entry_time).total_seconds() / 3600
                holding_times.append(delta)
        avg_hold = sum(holding_times) / len(holding_times) if holding_times else 0.0

        return PerformanceMetrics(
            total_trades=total,
            wins=num_wins,
            losses=num_losses,
            win_rate=round(win_rate, 4),
            average_win_r=round(avg_win, 4),
            average_loss_r=round(avg_loss, 4),
            average_rr=round(avg_rr, 4),
            expectancy_r=round(expectancy, 4),
            profit_factor=round(profit_factor, 4),
            max_drawdown_r=round(max_dd, 4),
            max_drawdown_percent=round(max_dd_pct, 4),
            sharpe_like_ratio=round(sharpe, 4),
            consecutive_losses_max=max_consecutive,
            false_signal_rate=round(false_signal_rate, 4),
            average_holding_time_hours=round(avg_hold, 2),
        )
