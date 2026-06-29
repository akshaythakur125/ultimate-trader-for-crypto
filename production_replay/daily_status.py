"""Daily status — doctor-mode one-command progress check.

Usage:
    python -m production_replay.daily_status
"""

import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.evidence_ledger import read_latest_entry

MIN_TRADES = 100
MIN_DAYS = 30


def main():
    entry = read_latest_entry()

    if entry is None:
        print("=" * 50)
        print("  DAILY STATUS — no data yet")
        print("=" * 50)
        print("  Run: python -m production_replay.operator")
        print("=" * 50)
        return 0

    trades = entry.get("total_trades", 0)
    days = entry.get("calendar_days", 0)
    ev = entry.get("ev_r", 0)
    pf = entry.get("profit_factor", 0)
    dd = entry.get("max_drawdown_r", 0)
    kill = entry.get("kill_status") == "KILL"
    safe = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED"
    paper_unlock = entry.get("paper_unlock_status") == "UNLOCKED"

    trades_ok = trades >= MIN_TRADES
    days_ok = days >= MIN_DAYS
    ev_ok = ev > 0
    pf_ok = pf >= 1.5
    dd_ok = dd < 12.0

    if paper_unlock and safe and ev_ok and pf_ok and dd_ok and not kill:
        next_action = "PAPER ELIGIBLE — run full paper pipeline"
    elif not safe:
        next_action = "INVESTIGATE — safety issue detected"
    elif trades_ok and days_ok:
        next_action = "WAIT — collecting more data"
    else:
        next_action = "WAIT — collecting data"

    print("=" * 50)
    print("  DAILY STATUS — " + entry.get("timestamp", "?")[:10])
    print("=" * 50)
    print(f"  Safe:      {'YES' if safe else 'NO'}")
    print(f"  Trades:    {trades}/{MIN_TRADES}")
    print(f"  Days:      {days}/{MIN_DAYS}")
    print(f"  EV:        {ev:+.3f}R")
    print(f"  PF:        {pf:.2f}")
    print(f"  DD:        {dd:.2f}R")
    print(f"  Kill:      {'YES' if kill else 'NO'}")
    print(f"  Paper:     {'ELIGIBLE' if paper_unlock else 'BLOCKED'}")
    print(f"  Live:      BLOCKED")
    print(f"  Mode:      {entry.get('mode', '?')}")
    print(f"  Commit:    {entry.get('git_commit', '?')}")
    print("-" * 50)
    print(f"  Next:      {next_action}")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
