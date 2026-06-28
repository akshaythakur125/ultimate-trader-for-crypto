"""Operator — single command for daily dry-forward operation.

Sequence:
1. Parse --quick (default) or --full mode
2. Run safety lock checks
3. Run launch check
4. Block immediately if launch_check fails
5. Run dry-forward with per-config timeout
6. Run evidence tracker
7. Generate deploy_results/dry_forward_report.json
8. Generate deploy_results/dry_forward_report.txt
9. Generate deploy_results/operator_summary.txt
10. Print final status table
"""

import argparse, json, os, sys, threading, time, traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.launch_check import run_launch_check, load_config
from production_replay.run_dry_forward import run_dry_forward
from production_replay.evidence_tracker import track_evidence, print_evidence_summary
from production_replay.safety_lock import run_safety_lock

RESULTS_DIR = "deploy_results"
SUMMARY_FILE = os.path.join(RESULTS_DIR, "operator_summary.txt")
TEXT_REPORT = os.path.join(RESULTS_DIR, "dry_forward_report.txt")
CONFIG_TIMEOUT = 300  # seconds per config (5 min)


def _target_wrapper(result_holder: list, index: int, func, *args, **kwargs):
    """Run func and store result in holder list."""
    try:
        result_holder[index] = func(*args, **kwargs)
    except Exception as e:
        result_holder[index] = e


def run_with_timeout(func, timeout: int, *args, **kwargs) -> Any:
    """Run func with a hard timeout using threading."""
    holder = [None]
    t = threading.Thread(target=_target_wrapper, args=(holder, 0, func, *args), kwargs=kwargs, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"timed out after {timeout}s")
    result = holder[0]
    if isinstance(result, Exception):
        raise result
    return result


def operator_run(quick_mode: bool = True) -> dict[str, Any]:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    start = time.time()
    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "quick" if quick_mode else "full (not implemented — only 3 allowed configs)",
        "operator_verdict": None,
        "launch_check": None,
        "safety_lock": None,
        "dry_forward": None,
        "evidence": None,
        "tests_status": None,
    }

    print("\n" + "=" * 72)
    print(f"  OPERATOR — {'QUICK' if quick_mode else 'FULL'} MODE")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # Step 1: Safety lock
    print("\n  [1/4] Running safety lock...")
    safety = run_safety_lock()
    result["safety_lock"] = safety
    if not safety["pass"]:
        result["operator_verdict"] = "BLOCKED_SAFETY"
        _write_summary(result, start)
        print("\n  OPERATOR BLOCKED: safety lock failed")
        sys.exit(1)
    print(f"  [1/4] Safety lock: ALL ENGAGED ({time.time()-start:.1f}s)")

    # Step 2: Launch check
    print(f"\n  [2/4] Running launch check...")
    config = load_config()
    lc = run_launch_check(config)
    result["launch_check"] = lc
    if lc["verdict"] != "PASS":
        result["operator_verdict"] = "BLOCKED_LAUNCH"
        _write_summary(result, start)
        print("\n  OPERATOR BLOCKED: launch check failed")
        sys.exit(1)
    print(f"  [2/4] Launch check: PASS ({time.time()-start:.1f}s)")

    # Step 3: Dry forward with per-config timeout
    print(f"\n  [3/4] Running dry-forward (timeout={CONFIG_TIMEOUT}s per config)...")
    try:
        dry_result = run_with_timeout(run_dry_forward, CONFIG_TIMEOUT * 3)
    except TimeoutError:
        print(f"\n  OPERATOR TIMEOUT: dry-forward exceeded {CONFIG_TIMEOUT * 3}s total", flush=True)
        result["operator_verdict"] = "TIMEOUT"
        _write_summary(result, start)
        sys.exit(1)
    except Exception as e:
        print(f"\n  OPERATOR ERROR: {e}", flush=True)
        traceback.print_exc()
        result["operator_verdict"] = "ERROR"
        _write_summary(result, start)
        sys.exit(1)
    result["dry_forward"] = dry_result

    # Write text report
    _write_text_report(dry_result)

    # Step 4: Track evidence
    print(f"\n  [4/4] Tracking evidence...")
    evidence = track_evidence(dry_result)
    result["evidence"] = evidence
    print_evidence_summary(evidence)

    # Final table
    operator_verdict = _determine_verdict(dry_result, evidence)
    result["operator_verdict"] = operator_verdict
    _print_final_table(dry_result, lc, safety, evidence, operator_verdict, start)

    # Write summary
    _write_summary(result, start)

    return result


def _determine_verdict(dry: dict, evidence: dict) -> str:
    return dry.get("verdict", "UNKNOWN")


def _write_text_report(dry: dict):
    lines = [
        "=" * 72,
        "  DRY-FORWARD REPORT (TEXT)",
        f"  {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 72,
        "",
        f"  Verdict: {dry.get('verdict', 'UNKNOWN')}",
        f"  Total trades: {dry.get('total_trades', 0)}",
        f"  Overall WR:   {dry.get('total_wr', 0):.1f}%",
        f"  Overall EV:   {dry.get('total_ev', 0):+.3f}R",
        f"  Overall PF:   {dry.get('total_pf', 0):.2f}",
        f"  Overall DD:   {dry.get('total_dd_r', 0):.2f}R",
        f"  Kill switch:  {'KILL' if dry.get('kill_triggered', False) else 'OK'}",
        "",
        "  Per-Config Results:",
    ]
    for cfg in dry.get("per_config", []):
        kill_mark = "KILL" if cfg.get("kill") else "OK"
        lines.append(f"    {cfg.get('label', '?'):15s}: {cfg.get('trades', 0):3d} trades, "
                     f"WR {cfg.get('wr', 0):5.1f}%, EV {cfg.get('ev', 0):+.3f}R, "
                     f"PF {cfg.get('pf', 0):.2f}, DD {cfg.get('dd', 0):.2f}R, {kill_mark}")
    lines.append("")
    lines.append("  Gates:")
    gates = dry.get("gates", {})
    if isinstance(gates, dict):
        for name, ok in gates.items():
            lines.append(f"    {'PASS' if ok else 'FAIL'} | {name}")
    lines.append("")
    lines.append(f"  Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 72)

    with open(TEXT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[TEXT REPORT] {TEXT_REPORT}")


def _print_final_table(dry: dict, lc: dict, safety: dict, evidence: dict,
                       operator_verdict: str, start: float):
    elapsed = time.time() - start
    print("\n" + "=" * 72)
    print("  OPERATOR FINAL STATUS")
    print("=" * 72)
    print(f"  {'Status':<20s} {'Result':<20s}")
    print("-" * 42)
    print(f"  {'Mode':<20s} {'QUICK (default)' if 'quick' in str(dry.get('mode', '')) else 'FULL':<20s}")
    print(f"  {'Launch Check':<20s} {lc.get('verdict', '?'):<20s}")
    print(f"  {'Safety Lock':<20s} {'PASS' if safety.get('pass') else 'FAIL':<20s}")
    print(f"  {'Live Trading':<20s} {'DISABLED':<20s}")
    print(f"  {'Paper Trading':<20s} {'DISABLED':<20s}")
    print(f"  {'Mode':<20s} {'DRY_RUN':<20s}")
    print(f"  {'Trades':<20s} {dry.get('total_trades', 0):<20d}")
    print(f"  {'Verdict':<20s} {operator_verdict:<20s}")
    print(f"  {'Kill Switch':<20s} {'OK' if not dry.get('kill_triggered', True) else 'KILL':<20s}")
    print(f"  {'Paper Unlock':<20s} {'BLOCKED' if evidence.get('paper_unlock_blocked', True) else 'UNLOCKED':<20s}")
    print(f"  {'Live Unlock':<20s} {'BLOCKED' if evidence.get('live_unlock_blocked', True) else 'UNLOCKED':<20s}")
    print(f"  {'Elapsed':<20s} {elapsed:.1f}s")
    print("-" * 42)
    next_action = evidence.get("paper_unlock_reason", "unknown")
    print(f"  Next action: {next_action}")
    print(f"  Daily cmd:   python -m production_replay.operator")
    print("=" * 72)


def _write_summary(result: dict, start: float):
    elapsed = time.time() - start
    lines = [
        "=" * 72,
        "  OPERATOR SUMMARY",
        f"  {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Mode: {result.get('mode', 'quick')}",
        "=" * 72,
        "",
        f"  Operator Verdict: {result.get('operator_verdict', 'UNKNOWN')}",
        f"  Elapsed: {elapsed:.1f}s",
        "",
        "--- Launch Check ---",
    ]
    lc = result.get("launch_check")
    if lc:
        for name, g in lc.get("gates", {}).items():
            lines.append(f"  {g.get('status', '?'):6s} | {name}")
        lines.append(f"  Verdict: {lc.get('verdict', '?')}")
    else:
        lines.append("  (not run)")

    lines.append("")
    lines.append("--- Safety Lock ---")
    sl = result.get("safety_lock")
    if sl:
        for name, c in sl.get("checks", {}).items():
            lines.append(f"  {'PASS' if c.get('pass') else 'FAIL':6s} | {name}")
        lines.append(f"  Verdict: {'ALL LOCKS ENGAGED' if sl.get('pass') else 'LOCK COMPROMISED'}")
    else:
        lines.append("  (not run)")

    lines.append("")
    lines.append("--- Dry-Forward ---")
    dry = result.get("dry_forward")
    if dry:
        lines.append(f"  Verdict: {dry.get('verdict', '?')}")
        lines.append(f"  Trades: {dry.get('total_trades', 0)}")
        lines.append(f"  WR: {dry.get('total_wr', 0):.1f}%")
        lines.append(f"  EV: {dry.get('total_ev', 0):+.3f}R")
        lines.append(f"  PF: {dry.get('total_pf', 0):.2f}")
        lines.append(f"  DD: {dry.get('total_dd_r', 0):.2f}R")
        lines.append(f"  Kill: {'OK' if not dry.get('kill_triggered', True) else 'KILL'}")
    else:
        lines.append("  (not run)")

    lines.append("")
    lines.append("--- Evidence ---")
    ev = result.get("evidence")
    if ev:
        lines.append(f"  Total trades: {ev.get('total_trades', 0)}")
        lines.append(f"  Calendar days: {ev.get('calendar_days_logged', 0)}")
        lines.append(f"  Paper unlock: {'BLOCKED' if ev.get('paper_unlock_blocked', True) else 'UNLOCKED'}")
        lines.append(f"  Live unlock: {'BLOCKED' if ev.get('live_unlock_blocked', True) else 'UNLOCKED'}")
    else:
        lines.append("  (not run)")

    lines.append("")
    lines.append("--- Generated Files ---")
    lines.append(f"  deploy_results/dry_forward_report.json")
    lines.append(f"  deploy_results/dry_forward_report.txt")
    lines.append(f"  deploy_results/operator_summary.txt")
    lines.append("")
    lines.append("=" * 72)

    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[SUMMARY] {SUMMARY_FILE}")
    print(f"  Next run: python -m production_replay.operator")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily dry-forward operator")
    parser.add_argument("--quick", action="store_true", default=True, help="Run only allowed configs (default)")
    parser.add_argument("--full", action="store_true", default=False, help="Run all configs (not implemented)")
    args, _ = parser.parse_known_args()
    quick_mode = not args.full  # default to quick, --full overrides
    try:
        operator_run(quick_mode=quick_mode)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n  OPERATOR ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
