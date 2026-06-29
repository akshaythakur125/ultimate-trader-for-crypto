"""Evidence ledger — persistent record of daily operator runs.

Appends one JSONL entry per completed operator run to
runtime_state/evidence_ledger.jsonl.

Usage:
    from production_replay.evidence_ledger import append_ledger_entry, read_latest_entry, generate_daily_brief
"""

import json, os, subprocess, sys
from datetime import datetime

LEDGER_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
LEDGER_FILE = os.environ.get("EVIDENCE_LEDGER_PATH") or os.path.join(LEDGER_DIR, "evidence_ledger.jsonl")
BRIEF_FILE = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "daily_brief.txt")

MIN_TRADES = 100
MIN_DAYS = 30


def _get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def append_ledger_entry(operator_result: dict) -> dict:
    """Append one JSONL entry from operator result. Returns the entry dict."""
    dry = operator_result.get("dry_forward", {})
    evidence = operator_result.get("evidence", {})
    safety = operator_result.get("safety_lock", {})
    lc = operator_result.get("launch_check", {})
    per_config = []
    for cfg in dry.get("per_config", []):
        per_config.append({
            "label": cfg.get("label", "?"),
            "status": cfg.get("status", "?"),
            "trades": cfg.get("trades", 0),
            "wr": cfg.get("wr", 0),
            "ev": cfg.get("ev", 0),
            "pf": cfg.get("pf", 0),
            "dd": cfg.get("dd", 0),
        })

    entry = {
        "timestamp": datetime.now().isoformat(),
        "git_commit": _get_git_commit(),
        "mode": operator_result.get("mode", "unknown"),
        "safety_lock_verdict": "ALL LOCKS ENGAGED" if safety.get("pass") else "LOCK COMPROMISED",
        "launch_check_verdict": lc.get("verdict", "?"),
        "dry_forward_verdict": dry.get("verdict", "?"),
        "total_trades": dry.get("total_trades", 0),
        "calendar_days": evidence.get("calendar_days_logged", 0),
        "win_rate": dry.get("total_wr", 0),
        "ev_r": dry.get("total_ev", 0),
        "profit_factor": dry.get("total_pf", 0),
        "max_drawdown_r": dry.get("total_dd_r", 0),
        "kill_status": "KILL" if dry.get("kill_triggered") else "OK",
        "paper_unlock_status": "BLOCKED" if evidence.get("paper_unlock_blocked", True) else "UNLOCKED",
        "live_unlock_status": "BLOCKED",
        "per_config": per_config,
        "live_trading_enabled": dry.get("live_trading_enabled", False),
        "paper_trading_enabled": dry.get("paper_trading_enabled", False),
    }

    os.makedirs(LEDGER_DIR, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_latest_entry() -> dict | None:
    """Read the most recent ledger entry, or None if empty."""
    if not os.path.exists(LEDGER_FILE):
        return None
    with open(LEDGER_FILE) as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def read_all_entries() -> list[dict]:
    """Read all ledger entries."""
    if not os.path.exists(LEDGER_FILE):
        return []
    with open(LEDGER_FILE) as f:
        return [json.loads(l) for l in f if l.strip()]


def generate_daily_brief(operator_result: dict | None = None) -> str:
    """Generate a short daily brief file. Uses operator_result or latest ledger entry."""
    entry = None
    if operator_result:
        entry = append_ledger_entry(operator_result)
    else:
        entry = read_latest_entry()

    if entry is None:
        text = (
            "NO DATA — Run python -m production_replay.operator first\n"
        )
    else:
        trades = entry.get("total_trades", 0)
        days = entry.get("calendar_days", 0)
        ev = entry.get("ev_r", 0)
        pf = entry.get("profit_factor", 0)
        dd = entry.get("max_drawdown_r", 0)
        safe = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED" and entry.get("launch_check_verdict") == "PASS"
        live_ok = not entry.get("live_trading_enabled", False)
        paper_ok = not entry.get("paper_trading_enabled", False)
        kill = entry.get("kill_status") == "KILL"

        # Determine final instruction
        trades_ok = trades >= MIN_TRADES
        days_ok = days >= MIN_DAYS
        ev_ok = ev > 0
        pf_ok = pf >= 1.5
        dd_ok = dd < 12.0
        all_gates = trades_ok and days_ok and ev_ok and pf_ok and dd_ok and not kill
        if not safe or not live_ok or not paper_ok:
            instruction = "INVESTIGATE"
        elif all_gates:
            instruction = "PAPER ELIGIBLE"
        elif trades_ok and days_ok:
            instruction = "WAIT (gates not met)"
        else:
            instruction = "WAIT (collecting data)"

        # Per-config status
        config_lines = []
        for cfg in entry.get("per_config", []):
            config_lines.append(f"  {cfg['label']:15s}: {cfg['status']:12s} | {cfg['trades']:3d} trades")

        text = (
            f"DAILY DOCTOR BRIEF\n"
            f"==================\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"\n"
            f"SYSTEM SAFE    | {'YES' if safe else 'NO'}\n"
            f"LIVE DISABLED  | {'YES' if live_ok else 'NO'}\n"
            f"PAPER DISABLED | {'YES' if paper_ok else 'NO'}\n"
            f"\n"
            f"Latest Trades:   {trades} / {MIN_TRADES} (need {max(0, MIN_TRADES - trades)} more)\n"
            f"Latest Days:     {days} / {MIN_DAYS} (need {max(0, MIN_DAYS - days)} more)\n"
            f"Latest EV:       {ev:+.3f}R\n"
            f"Latest PF:       {pf:.2f}\n"
            f"Latest DD:       {dd:.2f}R\n"
            f"Kill Switch:     {kill}\n"
            f"\n"
            f"Per-Config:\n"
        )
        text += "\n".join(config_lines) + "\n"
        text += (
            f"\n"
            f"FINAL INSTRUCTION: {instruction}\n"
        )

    os.makedirs(os.path.dirname(BRIEF_FILE), exist_ok=True)
    with open(BRIEF_FILE, "w") as f:
        f.write(text)
    return text
