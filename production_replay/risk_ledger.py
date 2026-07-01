"""Risk ledger — tracks daily/weekly PnL, trade count, cooldown, consecutive losses.

Usage:
    from production_replay.risk_ledger import RiskLedger
"""

import json, os
from datetime import datetime, timedelta

STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
LEDGER_PATH = os.path.join(STATE_DIR, "risk_ledger.jsonl")

MAX_LIVE_TRADES = 1
MAX_LOSSES_PER_DAY = 2
MAX_DAILY_LOSS_USDT = 2.0
MAX_WEEKLY_LOSS_USDT = 5.0
COOLDOWN_MINUTES = 60


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _this_week() -> str:
    return datetime.now().strftime("%Y-W%W")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _load_ledger() -> list[dict]:
    try:
        with open(LEDGER_PATH) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _append_ledger(entry: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


class RiskLedger:
    def __init__(self):
        self.entries = _load_ledger()
        self._today = _today()
        self._this_week = _this_week()

    def record_exit(self, symbol: str, direction: str, pnl_usdt: float,
                    exit_reason: str):
        entry = {
            "timestamp": _now_iso(),
            "date": self._today,
            "week": self._this_week,
            "symbol": symbol,
            "direction": direction,
            "pnl_usdt": round(pnl_usdt, 2),
            "exit_reason": exit_reason,
        }
        _append_ledger(entry)
        self.entries.append(entry)

    def record_error(self, message: str):
        entry = {
            "timestamp": _now_iso(),
            "date": self._today,
            "week": self._this_week,
            "type": "error",
            "message": message,
        }
        _append_ledger(entry)
        self.entries.append(entry)

    @property
    def today_pnl(self) -> float:
        return round(sum(e.get("pnl_usdt", 0) for e in self.entries
                         if e.get("date") == self._today and "pnl_usdt" in e), 2)

    @property
    def week_pnl(self) -> float:
        return round(sum(e.get("pnl_usdt", 0) for e in self.entries
                         if e.get("week") == self._this_week and "pnl_usdt" in e), 2)

    @property
    def today_trade_count(self) -> int:
        return sum(1 for e in self.entries
                   if e.get("date") == self._today and "pnl_usdt" in e)

    @property
    def today_loss_count(self) -> int:
        return sum(1 for e in self.entries
                   if e.get("date") == self._today
                   and e.get("pnl_usdt", 0) < 0)

    @property
    def consecutive_losses(self) -> int:
        count = 0
        for e in reversed(self.entries):
            pnl = e.get("pnl_usdt")
            if pnl is not None and pnl < 0:
                count += 1
            elif pnl is not None:
                break
        return count

    @property
    def last_trade_time(self) -> datetime | None:
        for e in reversed(self.entries):
            ts = e.get("timestamp")
            if ts and "pnl_usdt" in e:
                try:
                    return datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    pass
        return None

    @property
    def cooldown_active(self) -> bool:
        last = self.last_trade_time
        if not last:
            return False
        elapsed = datetime.now() - last
        return elapsed < timedelta(minutes=COOLDOWN_MINUTES)

    @property
    def cooldown_remaining_minutes(self) -> int:
        last = self.last_trade_time
        if not last:
            return 0
        elapsed = datetime.now() - last
        remaining = timedelta(minutes=COOLDOWN_MINUTES) - elapsed
        return max(0, int(remaining.total_seconds() // 60))

    @property
    def can_trade(self) -> bool:
        if self.today_loss_count >= MAX_LOSSES_PER_DAY:
            return False
        if self.today_pnl <= -MAX_DAILY_LOSS_USDT:
            return False
        if self.week_pnl <= -MAX_WEEKLY_LOSS_USDT:
            return False
        if self.cooldown_active:
            return False
        if self.consecutive_losses >= 2:
            return False
        return True

    def get_status_dict(self) -> dict:
        return {
            "today_pnl_usdt": self.today_pnl,
            "week_pnl_usdt": self.week_pnl,
            "today_trade_count": self.today_trade_count,
            "today_loss_count": self.today_loss_count,
            "consecutive_losses": self.consecutive_losses,
            "cooldown_active": self.cooldown_active,
            "cooldown_remaining_minutes": self.cooldown_remaining_minutes,
            "can_trade": self.can_trade,
            "max_live_trades": MAX_LIVE_TRADES,
            "max_losses_per_day": MAX_LOSSES_PER_DAY,
            "max_daily_loss_usdt": MAX_DAILY_LOSS_USDT,
            "max_weekly_loss_usdt": MAX_WEEKLY_LOSS_USDT,
            "cooldown_minutes": COOLDOWN_MINUTES,
        }
