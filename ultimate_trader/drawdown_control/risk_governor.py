from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection


RISK_MODES = ["NORMAL", "DEFENSIVE", "CAPITAL_PRESERVATION", "BLOCKED"]


@dataclass
class RiskGovernorConfig:
    max_daily_loss_r: float = 3.0
    max_weekly_loss_r: float = 6.0
    max_consecutive_losses_per_day: int = 2
    max_total_consecutive_losses: int = 5
    defensive_drawdown_threshold: float = 8.0
    capital_preservation_drawdown_threshold: float = 12.0
    rolling_10_negative_ev_reduce: bool = True
    rolling_20_pf_below_one_block: bool = True


@dataclass
class RiskGovernorDecision:
    allowed: bool = True
    risk_mode: str = "NORMAL"
    rejection_reason: str = ""
    current_drawdown: float = 0.0
    daily_loss: float = 0.0
    weekly_loss: float = 0.0
    consecutive_losses: int = 0
    daily_consecutive_losses: int = 0
    rolling_expectancy: float = 0.0
    rolling_profit_factor: float = 0.0


class RiskGovernor:
    def __init__(self, config: Optional[RiskGovernorConfig] = None):
        self._cfg = config or RiskGovernorConfig()
        self._daily_trades: dict[str, list[ReplayTrade]] = {}
        self._weekly_trades: dict[str, list[ReplayTrade]] = {}
        self._consecutive_losses = 0
        self._daily_consecutive = 0
        self._last_day = ""
        self._cumulative_r = 0.0
        self._peak_r = 0.0
        self._all_trades: list[ReplayTrade] = []

    def reset(self):
        self._daily_trades.clear()
        self._weekly_trades.clear()
        self._consecutive_losses = 0
        self._daily_consecutive = 0
        self._last_day = ""
        self._cumulative_r = 0.0
        self._peak_r = 0.0
        self._all_trades.clear()

    @property
    def all_trades(self) -> list[ReplayTrade]:
        return list(self._all_trades)

    @property
    def current_drawdown(self) -> float:
        return self._peak_r - self._cumulative_r

    def check_state(self, timestamp, grade: str = "") -> RiskGovernorDecision:
        current_dd = self.current_drawdown
        day_key = timestamp.strftime("%Y-%m-%d")
        iso_key = timestamp.strftime("%Y-%W")
        if day_key != self._last_day:
            self._daily_consecutive = 0
            self._last_day = day_key
        daily_loss = sum(t.net_r for t in self._daily_trades.get(day_key, []))
        weekly_loss = sum(t.net_r for t in self._weekly_trades.get(iso_key, []))
        last10 = self._all_trades[-10:] if len(self._all_trades) >= 10 else self._all_trades
        roll_ev = sum(t.net_r for t in last10) / len(last10) if last10 else 0
        roll_20 = self._all_trades[-20:] if len(self._all_trades) >= 20 else self._all_trades
        wins20 = [t for t in roll_20 if t.net_r > 0]
        losses20 = [t for t in roll_20 if t.net_r <= 0]
        roll_pf = (sum(t.net_r for t in wins20) / abs(sum(t.net_r for t in losses20))
                   if sum(t.net_r for t in losses20) != 0 else 99.0)
        return self._build_decision(
            current_dd, daily_loss, weekly_loss,
            self._consecutive_losses, self._daily_consecutive,
            roll_ev, roll_pf, grade,
        )

    def _build_decision(self, current_dd, daily_loss, weekly_loss,
                         consec, daily_consec, roll_ev, roll_pf, grade="") -> RiskGovernorDecision:
        dec = RiskGovernorDecision(
            current_drawdown=round(current_dd, 2),
            daily_loss=round(daily_loss, 2),
            weekly_loss=round(weekly_loss, 2),
            consecutive_losses=consec,
            daily_consecutive_losses=daily_consec,
            rolling_expectancy=round(roll_ev, 3),
            rolling_profit_factor=round(roll_pf, 2),
        )
        total_trades = len(self._all_trades)

        if current_dd >= self._cfg.capital_preservation_drawdown_threshold:
            dec.allowed = False
            dec.risk_mode = "CAPITAL_PRESERVATION"
            dec.rejection_reason = f"Drawdown {current_dd:.1f}R >= {self._cfg.capital_preservation_drawdown_threshold}R CAPITAL_PRESERVATION"
            return dec

        if current_dd >= self._cfg.defensive_drawdown_threshold:
            if grade != "A_PLUS":
                dec.allowed = False
                dec.risk_mode = "DEFENSIVE"
                dec.rejection_reason = f"Drawdown {current_dd:.1f}R >= {self._cfg.defensive_drawdown_threshold}R DEFENSIVE: A_PLUS only"
                return dec

        if daily_loss <= -self._cfg.max_daily_loss_r:
            dec.allowed = False
            dec.risk_mode = "BLOCKED"
            dec.rejection_reason = f"Daily loss {daily_loss:.1f}R exceeds {self._cfg.max_daily_loss_r}R max"
            return dec

        if weekly_loss <= -self._cfg.max_weekly_loss_r:
            dec.allowed = False
            dec.risk_mode = "BLOCKED"
            dec.rejection_reason = f"Weekly loss {weekly_loss:.1f}R exceeds {self._cfg.max_weekly_loss_r}R max"
            return dec

        if consec >= self._cfg.max_total_consecutive_losses:
            dec.allowed = False
            dec.risk_mode = "BLOCKED"
            dec.rejection_reason = f"{consec} consecutive losses exceeds {self._cfg.max_total_consecutive_losses}"
            return dec

        if daily_consec >= self._cfg.max_consecutive_losses_per_day:
            dec.allowed = False
            dec.risk_mode = "BLOCKED"
            dec.rejection_reason = f"{daily_consec} daily consecutive losses exceeds {self._cfg.max_consecutive_losses_per_day}"
            return dec

        if self._cfg.rolling_10_negative_ev_reduce and total_trades >= 10 and roll_ev < 0:
            if grade != "A_PLUS":
                dec.allowed = False
                dec.risk_mode = "DEFENSIVE"
                dec.rejection_reason = f"Rolling 10-trade EV {roll_ev:.3f} < 0: A_PLUS only"
                return dec

        if self._cfg.rolling_20_pf_below_one_block and total_trades >= 20 and roll_pf < 1.0:
            dec.allowed = False
            dec.risk_mode = "BLOCKED"
            dec.rejection_reason = f"Rolling 20-trade PF {roll_pf:.2f} < 1.0: blocked"
            return dec

        return dec

    def evaluate(self, trade: ReplayTrade, grade: str = "") -> RiskGovernorDecision:
        self._all_trades.append(trade)
        self._cumulative_r += trade.net_r
        self._peak_r = max(self._peak_r, self._cumulative_r)
        current_dd = self._peak_r - self._cumulative_r

        day_key = trade.signal_time.strftime("%Y-%m-%d")
        iso_key = trade.signal_time.strftime("%Y-%W")
        if day_key not in self._daily_trades:
            self._daily_trades[day_key] = []
        if iso_key not in self._weekly_trades:
            self._weekly_trades[iso_key] = []
        self._daily_trades[day_key].append(trade)
        self._weekly_trades[iso_key].append(trade)

        if day_key != self._last_day:
            self._daily_consecutive = 0
            self._last_day = day_key

        if trade.net_r <= 0:
            self._consecutive_losses += 1
            self._daily_consecutive += 1
        else:
            self._consecutive_losses = 0

        daily_loss = sum(t.net_r for t in self._daily_trades.get(day_key, []))
        weekly_loss = sum(t.net_r for t in self._weekly_trades.get(iso_key, []))

        last10 = self._all_trades[-10:] if len(self._all_trades) >= 10 else self._all_trades
        roll_ev = sum(t.net_r for t in last10) / len(last10) if last10 else 0
        roll_20 = self._all_trades[-20:] if len(self._all_trades) >= 20 else self._all_trades
        wins20 = [t for t in roll_20 if t.net_r > 0]
        losses20 = [t for t in roll_20 if t.net_r <= 0]
        roll_pf = (sum(t.net_r for t in wins20) / abs(sum(t.net_r for t in losses20))
                   if sum(t.net_r for t in losses20) != 0 else 99.0)

        return self._build_decision(
            current_dd, daily_loss, weekly_loss,
            self._consecutive_losses, self._daily_consecutive,
            roll_ev, roll_pf, grade,
        )
