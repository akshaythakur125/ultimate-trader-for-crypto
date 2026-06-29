"""Operator — single command for daily dry-forward operation.

Sequence:
1. Parse args — default is VM_FAST (cache-only, no download, 60s per config)
2. Run safety lock checks
3. Run launch check
4. Block immediately if launch_check fails
5. Run each allowed config serially with per-config timeout
6. If one config times out, continue remaining (partial results)
7. Build consolidated report from per-config results
8. Track evidence
9. Write deploy_results/* files
10. Print final status table

Verdicts (overall operator):
  - READY_FOR_PAPER: trades >= 100, DD < 12R, PF >= 1.5, EV > 0, no kill
  - INSUFFICIENT_TRADES: total trades < 100
  - BLOCKED_LAUNCH: launch check failed
  - ERROR: timeouts, exceptions, or poor edge quality
  Never TIMEOUT — per-config timeout is handled gracefully.

Per-config status:
  - OK: completed with trades > 0
  - INSUFFICIENT_TRADES: completed with 0 trades
  - TIMEOUT: exceeded per-config timeout
  - SKIPPED: excluded from default run (VM slow — use --config for manual run)
  - ERROR: exception during run
"""

import argparse, json, os, sys, threading, time, traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.launch_check import run_launch_check, load_config
from production_replay.evidence_tracker import track_evidence, print_evidence_summary
from production_replay.evidence_ledger import append_ledger_entry, generate_daily_brief
from production_replay.safety_lock import run_safety_lock
from production_replay.forward_test_runner import run_forward_test
from production_replay.kill_switch import check_kill_switch

RESULTS_DIR = "deploy_results"
SUMMARY_FILE = os.path.join(RESULTS_DIR, "operator_summary.txt")
TEXT_REPORT = os.path.join(RESULTS_DIR, "dry_forward_report.txt")
JSON_REPORT = os.path.join(RESULTS_DIR, "dry_forward_report.json")
CONFIG_TIMEOUT = 60  # per-config forward test (cache-only, no download)
TOTAL_TIMEOUT = 240  # total operator hard cap

ALLOWED = [
    ("BTCUSDT", "15m", "BTC 15m"),
    ("BTCUSDT", "30m", "BTC 30m"),
    ("SOLUSDT", "15m", "SOL 15m"),  # available via --config SOL:15m or --unlimited
]

RISK_CFG = {"consecutive_loss_cap": {"max_losses": 6}}


def _target_wrapper(result_holder: list, index: int, func, *args, **kwargs):
    try:
        result_holder[index] = func(*args, **kwargs)
    except Exception as e:
        result_holder[index] = e


def run_with_timeout(func, timeout: int, *args, **kwargs) -> Any:
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


def print_sep(char="=", width=80):
    print(char * width)


_SKIP_REASON = "VM slow — use --config for manual run"


def _format_timed_out_result(label: str, symbol: str, timeframe: str, t0: float) -> dict:
    return {
        "label": label, "symbol": symbol, "timeframe": timeframe,
        "status": "TIMEOUT",
        "trades": 0, "wr": 0, "ev": 0,
        "pf": 0, "dd": 0, "kill": False, "elapsed_s": round(time.time() - t0, 1),
        "windows": 0, "rejections": 0, "unique_rejected": 0,
    }


def _format_skipped_result(label: str, symbol: str, timeframe: str) -> dict:
    return {
        "label": label, "symbol": symbol, "timeframe": timeframe,
        "status": "SKIPPED",
        "trades": 0, "wr": 0, "ev": 0,
        "pf": 0, "dd": 0, "kill": False, "elapsed_s": 0,
        "windows": 0, "rejections": 0, "unique_rejected": 0,
        "skip_reason": _SKIP_REASON,
    }


def _compute_config_result(forward_result: dict, label: str) -> dict:
    trades = forward_result.get("trade_diagnostics", [])
    wins = sum(1 for t in trades if t["net_r"] > 0)
    wr = 100 * wins / len(trades) if trades else 0
    ev = sum(t["net_r"] for t in trades) / len(trades) if trades else 0
    wpnl = sum(t["net_r"] for t in trades if t["net_r"] > 0)
    lpnl = abs(sum(t["net_r"] for t in trades if t["net_r"] <= 0))
    pf = wpnl / lpnl if lpnl > 0 else (wpnl if wpnl > 0 else 0)

    cum = 0; peak = 0; dd = 0
    for t in trades:
        cum += t["net_r"]; peak = max(peak, cum); dd = max(dd, peak - cum)

    kill = check_kill_switch(trades=trades)
    rejections = forward_result.get("rejection_summary", [])

    window_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0, "dd": 0.0})
    for t in trades:
        w = t.get("window", "unknown")
        window_stats[w]["trades"] += 1
        window_stats[w]["wins"] += 1 if t["net_r"] > 0 else 0
        window_stats[w]["pnl"] += t["net_r"]

    for w in window_stats:
        w_trades = [t for t in trades if t.get("window") == w]
        wc = 0; wp = 0; wdd = 0
        for t in w_trades:
            wc += t["net_r"]; wp = max(wp, wc); wdd = max(wdd, wp - wc)
        window_stats[w]["dd"] = round(wdd, 2)

    has_trades = len(trades) > 0
    return {
        "label": label,
        "symbol": forward_result.get("symbol", "?"),
        "timeframe": forward_result.get("timeframe", "?"),
        "trades": len(trades),
        "wr": round(wr, 1),
        "ev": round(ev, 3),
        "pf": round(pf, 2),
        "dd": round(dd, 2),
        "kill": kill["kill_triggered"],
        "elapsed_s": forward_result.get("elapsed_s", 0),
        "windows": len(window_stats),
        "window_breakdown": {k: dict(v) for k, v in sorted(window_stats.items())},
        "rejections": len(rejections),
        "unique_rejected": forward_result.get("total_unique_rejected", 0),
        "status": "OK" if has_trades else "INSUFFICIENT_TRADES",
    }


def _build_consolidated_report(all_results: list[dict], all_trades: list[dict]) -> dict:
    total_trades = sum(r.get("trades", 0) for r in all_results)
    total_pnl = sum(t["net_r"] for t in all_trades) if all_trades else 0
    total_wins = sum(1 for t in all_trades if t["net_r"] > 0) if all_trades else 0
    total_wr = 100 * total_wins / len(all_trades) if all_trades else 0
    total_ev = total_pnl / len(all_trades) if all_trades else 0
    total_wpnl = sum(t["net_r"] for t in all_trades if t["net_r"] > 0) if all_trades else 0
    total_lpnl = abs(sum(t["net_r"] for t in all_trades if t["net_r"] <= 0)) if all_trades else 0
    total_pf = total_wpnl / total_lpnl if total_lpnl > 0 else 0
    cum = 0; peak = 0; total_dd = 0
    for t in all_trades:
        cum += t["net_r"]; peak = max(peak, cum); total_dd = max(total_dd, peak - cum)
    total_kill = check_kill_switch(trades=all_trades) if all_trades else {"kill_triggered": False}

    has_any_timeout = any(r.get("status") == "TIMEOUT" for r in all_results)
    has_any_error = any(r.get("status") == "ERROR" for r in all_results)

    evidence_ok = total_trades >= 100
    dd_ok = total_dd < 12.0
    dd_pref = total_dd < 8.0
    pf_ok = total_pf >= 1.5
    ev_ok = total_ev > 0

    # Determine report verdict: use trade-based verdict regardless of timeouts
    if total_trades == 0:
        report_verdict = "INSUFFICIENT_TRADES"
    elif evidence_ok and dd_ok and pf_ok and ev_ok and not total_kill["kill_triggered"]:
        report_verdict = "READY_FOR_PAPER"
    elif total_trades < 100:
        report_verdict = "INSUFFICIENT_TRADES"
    else:
        report_verdict = "ERROR"

    gates = {
        "Trades >= 100": evidence_ok,
        "DD < 12.0R": dd_ok,
        "DD < 8.0R (preferred)": dd_pref,
        "PF >= 1.5": pf_ok,
        "EV > 0": ev_ok,
        "Kill not triggered": not total_kill["kill_triggered"],
    }

    return {
        "mode": "dry_forward",
        "verdict": report_verdict,
        "timestamp": datetime.now().isoformat(),
        "configs_tested": len(all_results),
        "total_trades": total_trades,
        "total_wr": round(total_wr, 1),
        "total_ev": round(total_ev, 3),
        "total_pf": round(total_pf, 2),
        "total_dd_r": round(total_dd, 2),
        "kill_triggered": total_kill["kill_triggered"],
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "gates": gates,
        "per_config": all_results,
    }


def _write_text_report(report: dict):
    lines = [
        "=" * 72,
        "  DRY-FORWARD REPORT (TEXT)",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 72,
        "",
        f"  Verdict: {report.get('verdict', 'UNKNOWN')}",
        f"  Total trades: {report.get('total_trades', 0)}",
        f"  Overall WR:   {report.get('total_wr', 0):.1f}%",
        f"  Overall EV:   {report.get('total_ev', 0):+.3f}R",
        f"  Overall PF:   {report.get('total_pf', 0):.2f}",
        f"  Overall DD:   {report.get('total_dd_r', 0):.2f}R",
        f"  Kill switch:  {'KILL' if report.get('kill_triggered', False) else 'OK'}",
        "",
        "  Per-Config Results:",
    ]
    for cfg in report.get("per_config", []):
        status = cfg.get("status", "?")
        if status in ("OK", "INSUFFICIENT_TRADES"):
            kill_mark = "KILL" if cfg.get("kill") else "OK"
            lines.append(f"    {cfg.get('label', '?'):15s}: {cfg['status']:12s} | {cfg.get('trades', 0):3d} trades, "
                         f"WR {cfg.get('wr', 0):5.1f}%, EV {cfg.get('ev', 0):+.3f}R, "
                         f"PF {cfg.get('pf', 0):.2f}, DD {cfg.get('dd', 0):.2f}R, {kill_mark}")
        else:
            lines.append(f"    {cfg.get('label', '?'):15s}: {status}")
    lines.append("")
    lines.append("  Gates:")
    gates = report.get("gates", {})
    if isinstance(gates, dict):
        for name, ok in gates.items():
            lines.append(f"    {'PASS' if ok else 'FAIL'} | {name}")
    lines.append("")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 72)

    with open(TEXT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[TEXT REPORT] {TEXT_REPORT}")


def _write_summary(result: dict, start: float):
    elapsed = time.time() - start
    mode = result.get("mode", "fast_daily")
    lines = [
        "=" * 72,
        "  OPERATOR SUMMARY",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Mode: {mode}",
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
        lines.append("")
        lines.append("  Per-Config:")
        for cfg in dry.get("per_config", []):
            status = cfg.get("status", "?")
            trades = cfg.get("trades", 0)
            lines.append(f"    {cfg.get('label', '?'):15s}: {status:12s} | {trades:3d} trades")
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
    lines.append("--- Safety Status ---")
    lines.append(f"  Live trading:  {'DISABLED' if not dry or not dry.get('live_trading_enabled', False) else 'ENABLED'}")
    lines.append(f"  Paper trading: {'DISABLED' if not dry or not dry.get('paper_trading_enabled', False) else 'ENABLED'}")
    lines.append("")
    lines.append("")
    lines.append("--- Doctor Packet ---")
    dp = result.get("doctor_packet")
    if dp:
        lines.append(f"  Status: {dp.get('status', '?')}")
        lines.append(f"  Decision: {dp.get('decision', '?')}")
        lines.append(f"  Path: {dp.get('path', '?')}")
    else:
        lines.append("  (not run)")

    lines.append("")
    lines.append("--- Generated Files ---")
    lines.append(f"  {JSON_REPORT}")
    lines.append(f"  {TEXT_REPORT}")
    lines.append(f"  {SUMMARY_FILE}")
    lines.append("")
    lines.append("=" * 72)

    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[SUMMARY] {SUMMARY_FILE}")


def _print_final_table(dry: dict, lc: dict, safety: dict, evidence: dict,
                       operator_verdict: str, start: float, result: dict | None = None):
    elapsed = time.time() - start
    print_sep()
    print("  OPERATOR FINAL STATUS")
    print_sep()
    print(f"  {'Status':<20s} {'Result':<20s}")
    print("-" * 42)
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
    dp = result.get("doctor_packet", {}) if result else {}
    print(f"  {'Doctor Packet':<20s} {dp.get('status', 'N/A'):<20s}")
    print(f"  {'Final Decision':<20s} {dp.get('decision', 'N/A'):<20s}")
    print("-" * 42)
    print("  Per-Config:")
    for cfg in dry.get("per_config", []):
        status = cfg.get("status", "?")
        trades = cfg.get("trades", 0)
        print(f"    {cfg.get('label', '?'):15s}: {status:12s} | {trades:3d} trades")
    print("-" * 42)
    next_action = evidence.get("paper_unlock_reason", "unknown")
    print(f"  Next action: {next_action}")
    print(f"  Packet cmd:  cat deploy_results/doctor_daily_packet.txt")
    print(f"  Daily cmd:   python -m production_replay.operator")
    print_sep()


def _determine_operator_verdict(
    all_results: list[dict],
    dry_result: dict,
    evidence: dict,
) -> str:
    """Determine overall operator verdict. Never returns TIMEOUT."""
    # Completed = ran to completion (OK or INSUFFICIENT_TRADES)
    completed_configs = [r for r in all_results if r.get("status") in ("OK", "INSUFFICIENT_TRADES")]
    timed_out_configs = [r for r in all_results if r.get("status") == "TIMEOUT"]
    failed_configs = [r for r in all_results if r.get("status") == "ERROR"]

    any_timeout = len(timed_out_configs) > 0
    any_failure = len(failed_configs) > 0
    any_success = len(completed_configs) > 0
    all_failed = not any_success and (any_timeout or any_failure)

    if all_failed:
        return "ERROR"

    # Use the trade-based report verdict
    total_trades = dry_result.get("total_trades", 0)
    report_verdict = dry_result.get("verdict", "INSUFFICIENT_TRADES")

    if report_verdict == "READY_FOR_PAPER":
        return "READY_FOR_PAPER"
    elif report_verdict == "INSUFFICIENT_TRADES":
        return "INSUFFICIENT_TRADES"
    else:
        return "ERROR"


def operator_run(
    quick_mode: bool = True,
    config_labels: list[str] | None = None,
    fast_daily: bool = True,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    start = time.time()
    data_days = 75 if fast_daily else 365

    operator_result = {
        "timestamp": datetime.now().isoformat(),
        "mode": "fast_daily" if fast_daily else "unlimited",
        "operator_verdict": None,
        "launch_check": None,
        "safety_lock": None,
        "dry_forward": None,
        "evidence": None,
    }

    print_sep()
    mode_str = "VM_FAST" if fast_daily else "UNLIMITED"
    status_parts = []
    if allow_dirty:
        status_parts.append("DIRTY")
    status_tag = f" ({', '.join(status_parts)})" if status_parts else ""
    print(f"  OPERATOR — {mode_str} MODE{status_tag}")
    print(f"  Cache-only, no download | {CONFIG_TIMEOUT}s per config | Total cap {TOTAL_TIMEOUT}s")
    print(f"  Default configs: BTC 15m, BTC 30m (SOL 15m via --config)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_sep()

    # Step 1: Safety lock
    print(f"\n  {'='*60}")
    print(f"  [1/4] Running safety lock...")
    safety = run_safety_lock()
    operator_result["safety_lock"] = safety
    if not safety["pass"]:
        operator_result["operator_verdict"] = "ERROR"
        _write_summary(operator_result, start)
        print(f"\n  OPERATOR BLOCKED: safety lock failed")
        sys.exit(1)
    print(f"  [1/4] Safety lock: ALL ENGAGED ({time.time()-start:.1f}s)")

    # Step 2: Launch check
    print(f"\n  {'='*60}")
    print(f"  [2/4] Running launch check...")
    config = load_config()
    lc = run_launch_check(config, allow_dirty=allow_dirty)
    operator_result["launch_check"] = lc
    if lc["verdict"] != "PASS":
        operator_result["operator_verdict"] = "BLOCKED_LAUNCH"
        _write_summary(operator_result, start)
        print(f"\n  OPERATOR BLOCKED: launch check failed")
        sys.exit(1)
    print(f"  [2/4] Launch check: PASS ({time.time()-start:.1f}s)")

    # Step 3: Run each config serially (cache-only, no download, 60s per config)
    print(f"\n  {'='*60}")
    print(f"  [3/4] Running dry-forward (vm_fast, timeout={CONFIG_TIMEOUT}s per config)...")

    if config_labels:
        configs_to_run = [
            a for a in ALLOWED
            if a[2] in config_labels or f"{a[0]}:{a[1]}" in config_labels
        ]
        if not configs_to_run:
            print(f"  ERROR: no matching configs for {config_labels}")
            print(f"  Available: {[f'{s}:{tf}' for s,tf,_ in ALLOWED]}")
            sys.exit(1)
    else:
        # Default: only VM-reliable configs (SOL 15m is too slow for daily)
        configs_to_run = [a for a in ALLOWED if a[2] != "SOL 15m"]

    all_results: list[dict] = []
    all_trades: list[dict] = []

    for symbol, timeframe, label in configs_to_run:
        # Check total timeout before each config
        if time.time() - start >= TOTAL_TIMEOUT:
            print(f"\n  TOTAL TIMEOUT ({TOTAL_TIMEOUT}s) — skipping remaining configs", flush=True)
            break

        print(f"\n  [{label}] Starting (timeout={CONFIG_TIMEOUT}s)...")
        t0 = time.time()
        out_dir = os.path.join(RESULTS_DIR, f"{symbol}_{timeframe}")
        os.makedirs(out_dir, exist_ok=True)

        try:
            forward_result = run_with_timeout(
                run_forward_test, CONFIG_TIMEOUT,
                symbol=symbol, timeframe=timeframe,
                data_days=data_days,
                dry_run=False, output_dir=out_dir,
                risk_controls=RISK_CFG,
                fast_daily=fast_daily,
                vm_fast=True,
            )

            elapsed = time.time() - t0
            config_entry = _compute_config_result(forward_result, label)
            all_results.append(config_entry)
            all_trades.extend(forward_result.get("trade_diagnostics", []))

            status_mark = "KILL" if config_entry["kill"] else "OK"
            print(f"  -> {label}: {config_entry['trades']} trades, "
                  f"EV {config_entry['ev']:+.3f}R, PF {config_entry['pf']:.2f}, "
                  f"DD {config_entry['dd']:.2f}R, {status_mark} ({elapsed:.1f}s)")

            for wname, ws in sorted(config_entry.get("window_breakdown", {}).items()):
                wwr = 100 * ws["wins"] / ws["trades"] if ws["trades"] else 0
                print(f"     Window {wname[:20]:20s}: {ws['trades']:2d} trades, "
                      f"WR {wwr:5.1f}%, PnL {ws['pnl']:+7.2f}R, DD {ws['dd']:5.2f}R")

        except TimeoutError:
            print(f"  TIMEOUT: {label} exceeded {CONFIG_TIMEOUT}s — continuing")
            all_results.append(_format_timed_out_result(label, symbol, timeframe, t0))
        except Exception as e:
            print(f"  ERROR: {label}: {e}")
            all_results.append({
                "label": label, "symbol": symbol, "timeframe": timeframe,
                "status": "ERROR",
                "trades": 0, "wr": 0, "ev": 0,
                "pf": 0, "dd": 0, "kill": False, "elapsed_s": round(time.time() - t0, 1),
                "windows": 0, "rejections": 0, "unique_rejected": 0,
            })

    # In default mode, add SKIPPED entry for SOL 15m (VM slow — visible in output)
    if not config_labels:
        skipped = _format_skipped_result("SOL 15m", "SOLUSDT", "15m")
        all_results.append(skipped)
        print(f"\n  [SOL 15m] SKIPPED — {_SKIP_REASON}")

    # Build consolidated report
    dry_result = _build_consolidated_report(all_results, all_trades)
    operator_result["dry_forward"] = dry_result

    # Write JSON report
    with open(JSON_REPORT, "w") as f:
        json.dump(dry_result, f, indent=2)
    print(f"\n[JSON REPORT] {JSON_REPORT}")

    # Write text report
    _write_text_report(dry_result)

    # Print consolidated table
    print_sep()
    print("  CONSOLIDATED REPORT")
    print_sep()
    header = f"{'Config':<15s} {'Status':<12s} {'Trades':>6s} {'WR%':>5s} {'EV(R)':>8s} {'PF':>6s} {'DD(R)':>7s}"
    print(f"\n{header}")
    print("-" * 65)
    for r in all_results:
        status = r.get("status", r.get("error", "?"))
        if status not in ("OK", "INSUFFICIENT_TRADES"):
            print(f"{r['label']:<15s} {status:<12s} {'ERR':>6s} {'':>5s} {'':>8s} {'':>6s} {'':>7s}")
        else:
            km = "KILL" if r.get("kill") else "OK"
            print(f"{r['label']:<15s} {status:<12s} {r['trades']:>6d} {r['wr']:>5.1f} {r['ev']:+>8.3f} "
                  f"{r['pf']:>6.2f} {r['dd']:>7.2f}")
    total_t = dry_result.get("total_trades", 0)
    print("-" * 65)
    print(f"{'COMBINED':<15s} {'':<12s} {total_t:>6d}")

    print_sep()
    print("  GATES")
    print_sep()
    for name, ok in dry_result.get("gates", {}).items():
        print(f"  {'PASS' if ok else 'FAIL':6s} | {name}")
    print(f"\n  VERDICT: {dry_result['verdict']}")
    print_sep()

    # Step 4: Track evidence (uses only completed config trades via all_trades)
    print(f"\n  {'='*60}")
    print(f"  [4/4] Tracking evidence...")
    evidence = track_evidence(dry_result)
    operator_result["evidence"] = evidence
    print_evidence_summary(evidence)

    # Append to evidence ledger and generate daily brief
    append_ledger_entry(operator_result)
    brief = generate_daily_brief(operator_result)
    print(f"\n[DAILY BRIEF] {os.path.join(RESULTS_DIR, 'daily_brief.txt')}")

    # Step 5: Auto-generate doctor daily packet
    print(f"\n  {'='*60}")
    print(f"  [5/5] Generating doctor daily packet...")
    doctor_packet_ok = True
    doctor_packet_path = os.path.join(RESULTS_DIR, "doctor_daily_packet.txt")
    try:
        from production_replay.strategy_tournament import main as tournament_main
        tournament_main()
    except Exception as e:
        print(f"  WARNING: strategy_tournament failed: {e}", file=sys.stderr)
    try:
        from production_replay.doctor_daily_packet import main as ddp_main
        ddp_main()
        print(f"  [5/5] Doctor daily packet generated: {doctor_packet_path} ({time.time()-start:.1f}s)")
    except Exception as e:
        print(f"  ERROR: doctor_daily_packet generation failed: {e}", file=sys.stderr)
        doctor_packet_ok = False

    doctor_packet_status = "GENERATED" if doctor_packet_ok else "FAILED"
    doctor_final_decision = "UNKNOWN"
    if doctor_packet_ok:
        try:
            doctor_json = os.path.join(RESULTS_DIR, "doctor_daily_packet.json")
            if os.path.exists(doctor_json):
                with open(doctor_json) as f:
                    dp = json.load(f)
                doctor_final_decision = dp.get("final_decision", "UNKNOWN")
        except Exception:
            pass

    operator_result["doctor_packet"] = {
        "status": doctor_packet_status,
        "decision": doctor_final_decision,
        "path": doctor_packet_path,
    }

    # Determine overall operator verdict (never TIMEOUT)
    operator_verdict = _determine_operator_verdict(all_results, dry_result, evidence)
    operator_result["operator_verdict"] = operator_verdict
    _print_final_table(dry_result, lc, safety, evidence, operator_verdict, start, result=operator_result)
    _write_summary(operator_result, start)

    return operator_result


def _parse_config_labels(args_config: list[str] | None) -> list[str] | None:
    if not args_config:
        return None
    labels = []
    for c in args_config:
        c = c.strip()
        parts = c.replace(":", " ").replace("-", " ").split()
        if len(parts) == 1:
            labels.append(c)
        else:
            matched = False
            for sym, tf, lab in ALLOWED:
                if parts[0].upper() in sym and parts[1] == tf:
                    labels.append(lab)
                    matched = True
                    break
            if not matched:
                labels.append(c)
    return labels if labels else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily dry-forward operator (default: VM_FAST)")
    parser.add_argument("--quick", action="store_true", default=True,
                        help="Run default configs (BTC 15m, BTC 30m)")
    parser.add_argument("--unlimited", action="store_true", default=False,
                        help="Use 365d download instead of cache (slow)")
    parser.add_argument("--config", action="append", default=None,
                        help="Specific config(s) to run, e.g. --config BTC:15m")
    parser.add_argument("--allow-dirty", action="store_true", default=False,
                        help="Skip git tree clean check (for testing)")
    args, _ = parser.parse_known_args()

    config_labels = _parse_config_labels(args.config)
    fast_daily = not args.unlimited

    try:
        operator_run(
            quick_mode=True, config_labels=config_labels,
            fast_daily=fast_daily, allow_dirty=args.allow_dirty,
        )
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n  OPERATOR ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
