"""
Phase 79 — Paper Signal Outcome Tracker
Tracks every paper/watchlist signal from open to close.
Calculates win rate, avg R, profit factor, max consecutive losses.
Minimum before live review: 30 closed signals, avg R > 0, PF > 1.15, max consec <= 8.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paper_execution_ledger import _read_portfolio

RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
OUTCOMES_FILE = os.path.join(RUNTIME_DIR, "paper_signal_outcomes.jsonl")

# Minimum thresholds for live review
MIN_CLOSED_SIGNALS = 30
MIN_AVG_R = 0.0
MIN_PROFIT_FACTOR = 1.15
MAX_CONSECUTIVE_LOSSES = 8


def _load_outcomes():
    """Load all outcomes from JSONL."""
    if not os.path.exists(OUTCOMES_FILE):
        return []
    outcomes = []
    with open(OUTCOMES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    outcomes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return outcomes


def _save_outcome(outcome):
    """Append a single outcome to JSONL."""
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(OUTCOMES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(outcome) + "\n")


def register_paper_signal(symbol, direction, entry, stop, target, setup_type, strategy_family, rr):
    """Register a new paper signal for tracking.
    Returns the signal_id.
    """
    signal_id = f"PS_{symbol}_{direction}_{int(datetime.now(timezone.utc).timestamp())}"
    outcome = {
        "signal_id": signal_id,
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
        "setup_type": setup_type,
        "strategy_family": strategy_family,
        "status": "PAPER_OPEN",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": None,
        "r_multiple": None,
        "pnl_usdt": None,
    }
    _save_outcome(outcome)
    return signal_id


def update_signal_outcome(symbol, direction, new_status, current_price=None):
    """Update signal status when price hits target/stop or expires.
    Returns updated outcome or None if not found.
    """
    outcomes = _load_outcomes()
    updated = None

    for i, o in enumerate(outcomes):
        if (o.get("symbol") == symbol and
            o.get("direction") == direction and
            o.get("status") == "PAPER_OPEN"):

            entry = o.get("entry", 0)
            stop = o.get("stop", 0)
            target = o.get("target", 0)

            # Calculate R-multiple
            if new_status == "TARGET_HIT" and target != entry:
                r_multiple = abs(target - entry) / abs(entry - stop) if entry != stop else 0
                pnl = abs(target - entry)
            elif new_status == "STOP_HIT" and stop != entry:
                r_multiple = -1.0
                pnl = -(abs(entry - stop))
            elif new_status == "EXPIRED":
                if current_price and entry:
                    r_multiple = (current_price - entry) / abs(entry - stop) if entry != stop else 0
                    pnl = current_price - entry
                else:
                    r_multiple = 0
                    pnl = 0
            else:
                r_multiple = 0
                pnl = 0

            outcomes[i]["status"] = new_status
            outcomes[i]["closed_at"] = datetime.now(timezone.utc).isoformat()
            outcomes[i]["r_multiple"] = round(r_multiple, 4)
            outcomes[i]["pnl_usdt"] = round(pnl, 6)
            updated = outcomes[i]
            break

    if updated:
        # Rewrite entire file
        with open(OUTCOMES_FILE, "w", encoding="utf-8") as f:
            for o in outcomes:
                f.write(json.dumps(o) + "\n")

    return updated


def get_outcome_stats():
    """Calculate comprehensive outcome statistics.
    Returns dict with all stats.
    """
    outcomes = _load_outcomes()
    closed = [o for o in outcomes if o.get("status") in ("TARGET_HIT", "STOP_HIT", "EXPIRED")]

    if not closed:
        return {
            "total_signals": len(outcomes),
            "open_signals": sum(1 for o in outcomes if o.get("status") == "PAPER_OPEN"),
            "closed_signals": 0,
            "win_rate": 0,
            "avg_r": 0,
            "profit_factor": 0,
            "max_consecutive_losses": 0,
            "best_setup_type": "N/A",
            "worst_setup_type": "N/A",
            "live_review_ready": False,
            "requirements": {
                "closed_signals": f"0/{MIN_CLOSED_SIGNALS}",
                "avg_r": "0.0000",
                "profit_factor": "0.00",
                "max_consec_losses": "0",
            },
        }

    # Win rate
    wins = sum(1 for o in closed if o.get("status") == "TARGET_HIT")
    win_rate = wins / len(closed) if closed else 0

    # Average R
    avg_r = sum(o.get("r_multiple", 0) for o in closed) / len(closed) if closed else 0

    # Profit factor
    gains = sum(o.get("r_multiple", 0) for o in closed if o.get("r_multiple", 0) > 0)
    losses = abs(sum(o.get("r_multiple", 0) for o in closed if o.get("r_multiple", 0) < 0))
    pf = gains / losses if losses > 0 else 999

    # Max consecutive losses
    max_consec = 0
    current = 0
    for o in closed:
        if o.get("status") == "STOP_HIT" or o.get("r_multiple", 0) < 0:
            current += 1
            max_consec = max(max_consec, current)
        else:
            current = 0

    # Best/worst setup type
    setup_r = {}
    for o in closed:
        st = o.get("setup_type", "unknown")
        if st not in setup_r:
            setup_r[st] = []
        setup_r[st].append(o.get("r_multiple", 0))
    best = max(setup_r.items(), key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0) if setup_r else ("N/A", [])
    worst = min(setup_r.items(), key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0) if setup_r else ("N/A", [])

    # Live review readiness
    live_review_ready = (
        len(closed) >= MIN_CLOSED_SIGNALS and
        avg_r > MIN_AVG_R and
        pf > MIN_PROFIT_FACTOR and
        max_consec <= MAX_CONSECUTIVE_LOSSES
    )

    return {
        "total_signals": len(outcomes),
        "open_signals": sum(1 for o in outcomes if o.get("status") == "PAPER_OPEN"),
        "closed_signals": len(closed),
        "win_rate": round(win_rate, 4),
        "avg_r": round(avg_r, 4),
        "profit_factor": round(pf, 4),
        "max_consecutive_losses": max_consec,
        "best_setup_type": best[0] if isinstance(best, tuple) else "N/A",
        "worst_setup_type": worst[0] if isinstance(worst, tuple) else "N/A",
        "live_review_ready": live_review_ready,
        "requirements": {
            "closed_signals": f"{len(closed)}/{MIN_CLOSED_SIGNALS}",
            "avg_r": f"{avg_r:.4f}",
            "profit_factor": f"{pf:.2f}",
            "max_consec_losses": f"{max_consec}",
        },
    }


def get_active_signals():
    """Get all currently open signals."""
    outcomes = _load_outcomes()
    return [o for o in outcomes if o.get("status") == "PAPER_OPEN"]


def cleanup_expired_signals(max_age_hours=48):
    """Mark old open signals as EXPIRED if older than max_age_hours.
    Returns count of expired signals.
    """
    outcomes = _load_outcomes()
    now = datetime.now(timezone.utc)
    expired_count = 0

    for i, o in enumerate(outcomes):
        if o.get("status") != "PAPER_OPEN":
            continue
        opened = o.get("opened_at")
        if not opened:
            continue
        try:
            opened_dt = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            age_hours = (now - opened_dt).total_seconds() / 3600
            if age_hours > max_age_hours:
                outcomes[i]["status"] = "EXPIRED"
                outcomes[i]["closed_at"] = now.isoformat()
                outcomes[i]["r_multiple"] = 0
                outcomes[i]["pnl_usdt"] = 0
                expired_count += 1
        except Exception:
            continue

    if expired_count > 0:
        with open(OUTCOMES_FILE, "w", encoding="utf-8") as f:
            for o in outcomes:
                f.write(json.dumps(o) + "\n")

    return expired_count


def _get_outcomes_count():
    """Count lines in outcomes JSONL."""
    if not os.path.exists(OUTCOMES_FILE):
        return 0
    with open(OUTCOMES_FILE, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


if __name__ == "__main__":
    print("=" * 60)
    print("PAPER SIGNAL OUTCOME TRACKER")
    print("=" * 60)

    stats = get_outcome_stats()
    print(f"\nTotal signals: {stats['total_signals']}")
    print(f"Open signals: {stats['open_signals']}")
    print(f"Closed signals: {stats['closed_signals']}")
    print(f"Win rate: {stats['win_rate']:.1%}")
    print(f"Average R: {stats['avg_r']:.4f}")
    print(f"Profit factor: {stats['profit_factor']:.2f}")
    print(f"Max consecutive losses: {stats['max_consecutive_losses']}")
    print(f"Best setup: {stats['best_setup_type']}")
    print(f"Worst setup: {stats['worst_setup_type']}")
    print(f"\nLive review ready: {stats['live_review_ready']}")
    print("Requirements:")
    for k, v in stats["requirements"].items():
        print(f"  {k}: {v}")
