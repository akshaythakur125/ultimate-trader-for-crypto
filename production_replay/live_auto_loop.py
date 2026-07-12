"""Live automation loop — chains the gated pipeline on a fixed interval.

This is the single command for hands-off operation. It does NOT contain any
trade logic, gates, or risk limits of its own: every decision is delegated to
the existing modules (which enforce RR>=4, risk caps, stops, one position at a
time, kill switch, etc.). This script only sequences them and enforces that a
new entry is pursued only while the account is flat.

SAFETY — reads, never weakens, the same gates as the manual path:
  * No real order is ever placed unless BOTH are set in the environment:
        BINGX_EXECUTION_MODE=live_micro
        LIVE_TRADING_ACK=I_UNDERSTAND_THIS_CAN_LOSE_MONEY
    Without them the loop still runs signals + shadow + preflight and prints
    what it WOULD do, but bingx_live_micro_executor's own env gate blocks the
    order. This is the dry default.
  * If runtime_state/KILL_SWITCH_ON exists, the loop pursues no new entries.
  * A new entry is attempted only when no position is open (position monitor).

Each cycle:
  1. bingx_position_monitor  — refresh open-position state / manage exits
  2. if a position is open OR kill switch on: monitor only, then sleep
  3. otherwise (flat):
       trigger_watcher --once      — refresh live signals
       candidate_arbiter           — pick best candidate
       bingx_shadow_executor       — build SHADOW_READY intent (if any)
       bingx_live_preflight        — validate + size the order
       if PREFLIGHT_PASS and live env armed:
           live_one_shot_guard --arm
           bingx_live_micro_executor   — places the real order (all gates re-checked)
  4. sleep(--interval) and repeat

Depends on a reasonably fresh doctor_daily_packet.json (system_safe /
live_disabled / paper_disabled flags), which the daily operator run produces.
Run `python -m production_replay.operator` once a day alongside this loop.

Usage:
    python -m production_replay.live_auto_loop --interval 60          # dry
    BINGX_EXECUTION_MODE=live_micro LIVE_TRADING_ACK=I_UNDERSTAND_THIS_CAN_LOSE_MONEY \
        python -m production_replay.live_auto_loop --interval 60      # live micro
    python -m production_replay.live_auto_loop --once                 # single cycle
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = os.path.join(REPO, "deploy_results")
STATE_DIR = os.path.join(REPO, "runtime_state")
KILL_SWITCH_FILE = os.path.join(STATE_DIR, "KILL_SWITCH_ON")

ACK_VALUE = "I_UNDERSTAND_THIS_CAN_LOSE_MONEY"


def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _read_json(name: str) -> dict:
    try:
        with open(os.path.join(RESULTS_DIR, name)) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _run_module(name: str, args: list[str] | None = None, timeout: int = 90) -> bool:
    """Run `python -m production_replay.<name>` and return True on clean exit."""
    cmd = [sys.executable, "-m", f"production_replay.{name}"] + (args or [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
            _log(f"  {name}: exit {r.returncode} — {tail[0][:120]}")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        _log(f"  {name}: TIMEOUT after {timeout}s")
        return False
    except Exception as e:  # never let a helper crash the loop
        _log(f"  {name}: error {e}")
        return False


def _live_env_armed() -> bool:
    return (
        os.environ.get("BINGX_EXECUTION_MODE", "").lower() == "live_micro"
        and os.environ.get("LIVE_TRADING_ACK", "") == ACK_VALUE
    )


def _position_is_open() -> bool:
    st = _read_json("position_monitor_status.json")
    if st.get("position_found"):
        return True
    # Fall back to the last live-execution snapshot's open-position count.
    live = _read_json("bingx_live_execution.json")
    return int(live.get("open_position_count", 0) or 0) > 0


def run_cycle(live_armed: bool) -> str:
    """Run one full pipeline cycle. Returns a short status string."""
    # 1. Refresh position / exit management first.
    _run_module("bingx_position_monitor", ["--once"], timeout=60)

    # 2. Kill switch or open position -> monitor only.
    if os.path.exists(KILL_SWITCH_FILE):
        return "KILL_SWITCH_ON — monitoring only, no new entries"
    if _position_is_open():
        return "POSITION_OPEN — monitoring only, no new entries"

    # 3. Flat: refresh signals and build/validate an order intent.
    _run_module("trigger_watcher", ["--once"], timeout=120)
    _run_module("candidate_arbiter", timeout=90)
    _run_module("bingx_shadow_executor", timeout=90)

    shadow = _read_json("bingx_order_intent.json")
    if shadow.get("decision") != "SHADOW_READY":
        return f"NO_SIGNAL — shadow decision {shadow.get('decision', 'N/A')}"

    _run_module("bingx_live_preflight", timeout=90)
    preflight = _read_json("bingx_live_preflight.json")
    if not preflight.get("preflight_pass"):
        reasons = preflight.get("reasons", [])
        return f"PREFLIGHT_FAIL — {reasons[0] if reasons else 'checks failed'}"

    sym = preflight.get("symbol", "?")
    side = preflight.get("direction", "?")
    if not live_armed:
        return (f"DRY_READY — would place {side} {sym} "
                f"(set BINGX_EXECUTION_MODE=live_micro + LIVE_TRADING_ACK to go live)")

    # 4. Live micro: arm the one-shot guard and let the executor re-check every
    #    gate and place the order with its attached stop-loss and take-profit.
    _run_module("live_one_shot_guard", ["--arm"], timeout=30)
    _run_module("bingx_live_micro_executor", timeout=60)
    live = _read_json("bingx_live_execution.json")
    decision = live.get("decision", "N/A")
    if decision == "EXECUTED":
        return f"EXECUTED — {side} {sym} placed with stop + target"
    reasons = live.get("reasons", [])
    return f"EXECUTOR_{decision} — {reasons[0] if reasons else 'gates not passed'}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Live automation loop (dry unless env-armed)")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between cycles")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    args = parser.parse_args()

    live_armed = _live_env_armed()
    mode = "LIVE_MICRO (real orders enabled)" if live_armed else "DRY (no real orders)"
    _log(f"live_auto_loop starting — mode: {mode}, interval: {args.interval}s")
    if not live_armed:
        _log("  To enable real orders: set BINGX_EXECUTION_MODE=live_micro and "
             "LIVE_TRADING_ACK=" + ACK_VALUE)

    try:
        while True:
            status = run_cycle(live_armed)
            _log(f"cycle: {status}")
            if args.once:
                break
            time.sleep(max(5, args.interval))
    except KeyboardInterrupt:
        _log("stopped by user")
    return 0


if __name__ == "__main__":
    sys.exit(main())
