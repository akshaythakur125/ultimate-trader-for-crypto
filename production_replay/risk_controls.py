"""Phase 6 — Risk controls for cumulative drawdown reduction.

Each control is a stateless check function that receives the current
controller state and returns (allowed: bool, reason: str | None).

No signal logic changes. No indicator changes. No threshold tuning.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable


@dataclass
class TradeRecord:
    direction: str
    net_r: float
    timestamp: datetime
    day_key: str


@dataclass
class ControllerState:
    """Mutable state tracked across trades."""
    trades: list[TradeRecord] = field(default_factory=list)
    consecutive_losses: int = 0
    consecutive_losses_by_dir: dict[str, int] = field(default_factory=lambda: {"LONG": 0, "SHORT": 0})
    daily_pnl: dict[str, float] = field(default_factory=dict)
    candles_since_last_loss: int = 0
    candles_since_last_trade: int = 0
    current_candle_idx: int = 0
    current_window_trades: int = 0
    last_trade_direction: str | None = None
    last_trade_was_loss: bool = False

    def record_trade(self, direction: str, net_r: float, ts: datetime, day_key: str):
        self.trades.append(TradeRecord(direction, net_r, ts, day_key))
        self.last_trade_direction = direction
        self.candles_since_last_trade = 0
        if net_r <= 0:
            self.consecutive_losses += 1
            self.consecutive_losses_by_dir[direction] = self.consecutive_losses_by_dir.get(direction, 0) + 1
            self.candles_since_last_loss = 0
            self.last_trade_was_loss = True
        else:
            self.consecutive_losses = 0
            self.consecutive_losses_by_dir[direction] = 0
            self.last_trade_was_loss = False
        self.daily_pnl[day_key] = self.daily_pnl.get(day_key, 0) + net_r
        self.current_window_trades += 1

    def advance_candle(self):
        self.candles_since_last_trade += 1
        self.candles_since_last_loss += 1

    @property
    def cumulative_pnl(self) -> float:
        return sum(t.net_r for t in self.trades)

    @property
    def rolling_drawdown(self) -> float:
        peak = 0.0
        cum = 0.0
        max_dd = 0.0
        for t in self.trades:
            cum += t.net_r
            peak = max(peak, cum)
            max_dd = max(max_dd, peak - cum)
        return max_dd


def post_loss_cooldown(min_candles: int) -> Callable:
    """Skip trading for N candles after a losing trade."""
    def check(state: ControllerState, direction: str, candle_idx: int, **_kw) -> tuple[bool, str | None]:
        if state.last_trade_was_loss and state.candles_since_last_loss < min_candles:
            remaining = min_candles - state.candles_since_last_loss
            return False, f"post-loss cooldown ({remaining} candles remaining)"
        return True, None
    return check


def direction_cooldown_after_loss(min_candles: int) -> Callable:
    """Skip same-direction entries for N candles after a losing trade in that direction."""
    def check(state: ControllerState, direction: str, candle_idx: int, **_kw) -> tuple[bool, str | None]:
        last_loss_trade = None
        for t in reversed(state.trades):
            if t.net_r <= 0:
                last_loss_trade = t
                break
        if last_loss_trade and last_loss_trade.direction == direction:
            candles_since = state.current_candle_idx - _find_trade_idx(state, last_loss_trade)
            if candles_since < min_candles:
                remaining = min_candles - candles_since
                return False, f"direction cooldown {direction} ({remaining} candles remaining)"
        return True, None
    return check


def _find_trade_idx(state: ControllerState, target: TradeRecord) -> int:
    for i, t in enumerate(state.trades):
        if t is target:
            return i
    return 0


def consecutive_loss_cap(max_losses: int) -> Callable:
    """Stop trading for the rest of the day after N consecutive losses."""
    def check(state: ControllerState, direction: str, day_key: str, **_kw) -> tuple[bool, str | None]:
        if state.consecutive_losses >= max_losses:
            return False, f"{state.consecutive_losses} consecutive losses >= {max_losses} cap"
        return True, None
    return check


def daily_loss_cap(max_daily_loss_r: float) -> Callable:
    """Stop trading after losing more than M R in a single day."""
    def check(state: ControllerState, direction: str, day_key: str, **_kw) -> tuple[bool, str | None]:
        daily = state.daily_pnl.get(day_key, 0)
        if daily <= -max_daily_loss_r:
            return False, f"daily PnL {daily:.2f}R <= -{max_daily_loss_r:.1f}R cap"
        return True, None
    return check


def rolling_drawdown_throttle(max_dd_r: float) -> Callable:
    """Stop trading when cumulative drawdown exceeds threshold."""
    def check(state: ControllerState, direction: str, **_kw) -> tuple[bool, str | None]:
        dd = state.rolling_drawdown
        if dd >= max_dd_r:
            return False, f"rolling DD {dd:.2f}R >= {max_dd_r:.1f}R throttle"
        return True, None
    return check


def max_trades_per_window(max_trades: int) -> Callable:
    """Limit total trades per test window."""
    def check(state: ControllerState, direction: str, **_kw) -> tuple[bool, str | None]:
        if state.current_window_trades >= max_trades:
            return False, f"max trades per window ({max_trades}) reached"
        return True, None
    return check


CONTROL_REGISTRY: dict[str, Callable] = {
    "post_loss_cooldown": lambda cfg: post_loss_cooldown(cfg.get("min_candles", 3)),
    "direction_cooldown": lambda cfg: direction_cooldown_after_loss(cfg.get("min_candles", 5)),
    "consecutive_loss_cap": lambda cfg: consecutive_loss_cap(cfg.get("max_losses", 3)),
    "daily_loss_cap": lambda cfg: daily_loss_cap(cfg.get("max_daily_loss_r", 3.0)),
    "rolling_drawdown": lambda cfg: rolling_drawdown_throttle(cfg.get("max_dd_r", 8.0)),
    "max_trades_per_window": lambda cfg: max_trades_per_window(cfg.get("max_trades", 30)),
}


def build_controller(controls: dict[str, dict] | None) -> tuple[list[Callable], ControllerState]:
    """Build list of check functions from a controls config dict.
    
    Args:
        controls: Dict of {control_name: {param: value}}.
            None or empty = no controls.
    
    Returns:
        (list_of_check_fns, state)
    """
    checks: list[Callable] = []
    if not controls:
        return checks, ControllerState()
    for name, cfg in controls.items():
        builder = CONTROL_REGISTRY.get(name)
        if builder:
            checks.append(builder(cfg))
    return checks, ControllerState()
