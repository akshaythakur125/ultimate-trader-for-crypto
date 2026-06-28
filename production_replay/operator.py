"""Operator — single command for daily dry-forward operation.

Sequence:
1. Run safety lock checks
2. Run launch check
3. Block immediately if launch_check fails
4. Run dry-forward
5. Run evidence tracker
6. Generate deploy_results/dry_forward_report.json
7. Generate deploy_results/dry_forward_report.txt
8. Generate deploy_results/operator_summary.txt
9. Print final status table
"""

import json, os, sys, time, traceback
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


def operator_run() -> dict[str, Any]:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    start = time.time()
    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "operator_verdict": None,
        "launch_check": None,
        "safety_lock": None,
        "dry_forward": None,
        "evidence": None,
        "tests_status": None,
    }

    # Step 1: Safety lock
    print("\n")
    safety = run_safety_lock()
    result["safety_lock"] = safety
    if not safety["pass"]:
        result["operator_verdict"] = "BLOCKED_SAFETY"
        _write_summary(result, start)
        print("\n  OPERATOR BLOCKED: safety lock failed")
        sys.exit(1)

    # Step 2: Launch check
    config = load_config()
    lc = run_launch_check(config)
    result["launch_check"] = lc
    if lc["verdict"] != "PASS":
        result["operator_verdict"] = "BLOCKED_LAUNCH"
        _write_summary(result, start)
        print("\n  OPERATOR BLOCKED: launch check failed")
        sys.exit(1)

    # Step 3: Dry forward
    print("\n")
    dry = run_dry_forward()
    result["dry_forward"] = dry

    # Write text report
    _write_text_report(dry)

    # Step 4: Track evidence
    evidence = track_evidence(dry)
    result["evidence"] = evidence
    print("\n")
    print_evidence_summary(evidence)

    # Step 5: Print final table
    operator_verdict = _determine_verdict(dry, evidence)
    result["operator_verdict"] = operator_verdict
    _print_final_table(dry, lc, safety, evidence, operator_verdict, start)

    # Step 6: Write summary
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
    tests_ok = "N/A (run pytest separately)"
    print("\n" + "=" * 72)
    print("  OPERATOR FINAL STATUS")
    print("=" * 72)
    print(f"  {'Status':<20s} {'Result':<20s}")
    print("-" * 42)
    print(f"  {'Tests':<20s} {tests_ok:<20s}")
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
    print(f"  Daily cmd:   python production_replay/operator.py")
    print("=" * 72)


def _write_summary(result: dict, start: float):
    elapsed = time.time() - start
    lines = [
        "=" * 72,
        "  OPERATOR SUMMARY",
        f"  {time.strftime('%Y-%m-%d %H:%M:%S')}",
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
    lines.append(f"--- Generated Files ---")
    lines.append(f"  deploy_results/dry_forward_report.json")
    lines.append(f"  deploy_results/dry_forward_report.txt")
    lines.append(f"  deploy_results/operator_summary.txt")
    lines.append("")
    lines.append("=" * 72)

    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[SUMMARY] {SUMMARY_FILE}")
    print(f"  Next run: python production_replay/operator.py")


if __name__ == "__main__":
    try:
        operator_run()
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n  OPERATOR ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
