"""Operator — single command for daily dry-forward operation.

Sequence:
1. Parse --quick (default), --config <label>, or --fast mode
2. Run safety lock checks
3. Run launch check
4. Block immediately if launch_check fails
5. Run each allowed config serially with per-config timeout
6. If one config times out, continue remaining (partial results)
7. Build consolidated report from per-config results
8. Track evidence
9. Write deploy_results/* files
10. Print final status table

CLI:
  python -m production_replay.operator           # quick mode (all 3)
  python -m production_replay.operator --quick   # same
  python -m production_replay.operator --config BTC:15m
  python -m production_replay.operator --config BTC:15m --config BTC:30m
  python -m production_replay.operator --config SOL:15m
  python -m production_replay.operator --fast    # 180d cache, no 365d download
"""

import argparse, json, os, sys, threading, time, traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.launch_check import run_launch_check, load_config
from production_replay.evidence_tracker import track_evidence, print_evidence_summary
from production_replay.safety_lock import run_safety_lock
from production_replay.forward_test_runner import run_forward_test
from production_replay.kill_switch import check_kill_switch

RESULTS_DIR = "deploy_results"
SUMMARY_FILE = os.path.join(RESULTS_DIR, "operator_summary.txt")
TEXT_REPORT = os.path.join(RESULTS_DIR, "dry_forward_report.txt")
JSON_REPORT = os.path.join(RESULTS_DIR, "dry_forward_report.json")
CONFIG_TIMEOUT = 300  # seconds per config

ALLOWED = [
    ("BTCUSDT", "15m", "BTC 15m"),
    ("BTCUSDT", "30m", "BTC 30m"),
    ("SOLUSDT", "15m", "SOL 15m"),
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


def _compute_config_result(forward_result: dict, label: str) -> dict:
    """Build a per-config entry dict from a forward_test result."""
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
    }


def _build_consolidated_report(all_results: list[dict], all_trades: list[dict]) -> dict:
    """Build the final consolidated report from per-config results."""
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

    success_results = [r for r in all_results if "error" not in r]
    has_timeout = any(r.get("error") == "timeout" for r in all_results)
    has_error = any(r.get("error") not in (None, "timeout") for r in all_results)

    evidence_ok = total_trades >= 100
    dd_ok = total_dd < 12.0
    dd_pref = total_dd < 8.0
    pf_ok = total_pf >= 1.5
    ev_ok = total_ev > 0

    if has_timeout or has_error:
        verdict = "PARTIAL_TIMEOUT" if has_timeout else "PARTIAL_ERROR"
    elif evidence_ok and dd_ok and pf_ok and ev_ok and not total_kill["kill_triggered"]:
        verdict = "ROBUST_EDGE" if dd_pref else "REGIME_SPECIFIC_EDGE"
    elif total_trades < 100:
        verdict = "INSUFFICIENT_TRADES"
    elif total_dd >= 12.0 or total_ev <= 0 or total_pf < 1.5:
        verdict = "NO_EDGE"
    else:
        verdict = "REGIME_SPECIFIC_EDGE"

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
        "verdict": verdict,
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
        kill_mark = "KILL" if cfg.get("kill") else "OK"
        if "error" in cfg:
            lines.append(f"    {cfg.get('label', '?'):15s}: ERROR ({cfg.get('error', '?')})")
        else:
            lines.append(f"    {cfg.get('label', '?'):15s}: {cfg.get('trades', 0):3d} trades, "
                         f"WR {cfg.get('wr', 0):5.1f}%, EV {cfg.get('ev', 0):+.3f}R, "
                         f"PF {cfg.get('pf', 0):.2f}, DD {cfg.get('dd', 0):.2f}R, {kill_mark}")
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
    lines = [
        "=" * 72,
        "  OPERATOR SUMMARY",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
    lines.append(f"  {JSON_REPORT}")
    lines.append(f"  {TEXT_REPORT}")
    lines.append(f"  {SUMMARY_FILE}")
    lines.append("")
    lines.append("=" * 72)

    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[SUMMARY] {SUMMARY_FILE}")


def _print_final_table(dry: dict, lc: dict, safety: dict, evidence: dict,
                       operator_verdict: str, start: float):
    elapsed = time.time() - start
    print_sep()
    print("  OPERATOR FINAL STATUS")
    print_sep()
    print(f"  {'Status':<20s} {'Result':<20s}")
    print("-" * 42)
    print(f"  {'Mode':<20s} {'QUICK (default)' if dry.get('mode') == 'dry_forward' else 'FULL':<20s}")
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
    print_sep()


def operator_run(
    quick_mode: bool = True,
    config_labels: list[str] | None = None,
    fast_daily: bool = False,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    start = time.time()
    data_days = 180 if fast_daily else 365

    operator_result = {
        "timestamp": datetime.now().isoformat(),
        "mode": "fast_daily" if fast_daily else ("quick" if quick_mode else "custom"),
        "operator_verdict": None,
        "launch_check": None,
        "safety_lock": None,
        "dry_forward": None,
        "evidence": None,
    }

    print_sep()
    mode_str = "FAST DAILY (180d)" if fast_daily else ("QUICK" if quick_mode else "CUSTOM")
    status_parts = []
    if fast_daily:
        status_parts.append("FAST")
    if allow_dirty:
        status_parts.append("DIRTY")
    status_tag = f" ({', '.join(status_parts)})" if status_parts else ""
    print(f"  OPERATOR — {mode_str} MODE{status_tag}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_sep()

    # Step 1: Safety lock
    print(f"\n  {'='*60}")
    print(f"  [1/4] Running safety lock...")
    safety = run_safety_lock()
    operator_result["safety_lock"] = safety
    if not safety["pass"]:
        operator_result["operator_verdict"] = "BLOCKED_SAFETY"
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

    # Step 3: Run each config serially with per-config timeout
    print(f"\n  {'='*60}")
    print(f"  [3/4] Running dry-forward (timeout={CONFIG_TIMEOUT}s per config)...")

    # Resolve config list
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
        configs_to_run = ALLOWED

    all_results: list[dict] = []
    all_trades: list[dict] = []

    for symbol, timeframe, label in configs_to_run:
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
            all_results.append({
                "label": label, "symbol": symbol, "timeframe": timeframe,
                "error": "timeout", "trades": 0, "wr": 0, "ev": 0,
                "pf": 0, "dd": 0, "kill": False, "elapsed_s": round(time.time() - t0, 1),
                "windows": 0, "rejections": 0, "unique_rejected": 0,
            })
        except Exception as e:
            print(f"  ERROR: {label}: {e}")
            all_results.append({
                "label": label, "symbol": symbol, "timeframe": timeframe,
                "error": str(e), "trades": 0, "wr": 0, "ev": 0,
                "pf": 0, "dd": 0, "kill": False, "elapsed_s": round(time.time() - t0, 1),
                "windows": 0, "rejections": 0, "unique_rejected": 0,
            })

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
    header = f"{'Config':<15s} {'Trades':>6s} {'WR%':>5s} {'EV(R)':>8s} {'PF':>6s} {'DD(R)':>7s} {'Kill':>5s}"
    print(f"\n{header}")
    print("-" * 60)
    for r in all_results:
        if "error" in r:
            print(f"{r['label']:<15s} {'ERR':>6s} {'':>5s} {'':>8s} {'':>6s} {'':>7s} {'':>5s}  ({r.get('error', '?')})")
        else:
            km = "KILL" if r.get("kill") else "OK"
            print(f"{r['label']:<15s} {r['trades']:>6d} {r['wr']:>5.1f} {r['ev']:+>8.3f} "
                  f"{r['pf']:>6.2f} {r['dd']:>7.2f} {km:>5s}")
    total_t = dry_result.get("total_trades", 0)
    total_k = dry_result.get("kill_triggered", False)
    print("-" * 60)
    print(f"{'COMBINED':<15s} {total_t:>6d}")

    print_sep()
    print("  GATES")
    print_sep()
    for name, ok in dry_result.get("gates", {}).items():
        print(f"  {'PASS' if ok else 'FAIL':6s} | {name}")
    print(f"\n  VERDICT: {dry_result['verdict']}")
    print_sep()

    # Step 4: Track evidence
    print(f"\n  {'='*60}")
    print(f"  [4/4] Tracking evidence...")
    evidence = track_evidence(dry_result)
    operator_result["evidence"] = evidence
    print_evidence_summary(evidence)

    # Determine operator verdict
    has_timeout = any(r.get("error") == "timeout" for r in all_results)
    has_error = any(r.get("error") not in (None, "timeout") for r in all_results)
    has_success = any("error" not in r for r in all_results)

    if has_timeout and has_success:
        operator_verdict = "PARTIAL_TIMEOUT"
    elif has_timeout:
        operator_verdict = "TOTAL_TIMEOUT"
    elif has_error:
        operator_verdict = "ERROR"
    else:
        operator_verdict = dry_result["verdict"]

    operator_result["operator_verdict"] = operator_verdict
    _print_final_table(dry_result, lc, safety, evidence, operator_verdict, start)
    _write_summary(operator_result, start)

    return operator_result


def _parse_config_labels(args_config: list[str] | None) -> list[str] | None:
    """Normalize --config values to canonical labels."""
    if not args_config:
        return None
    labels = []
    for c in args_config:
        c = c.strip()
        # Accept "BTC:15m", "BTC 15m", "BTC15m", "BTC-15m"
        parts = c.replace(":", " ").replace("-", " ").split()
        if len(parts) == 1:
            labels.append(c)
        else:
            # Try to match against ALLOWED
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
    parser = argparse.ArgumentParser(description="Daily dry-forward operator")
    parser.add_argument("--quick", action="store_true", default=True,
                        help="Run all 3 allowed configs (default)")
    parser.add_argument("--full", action="store_true", default=False,
                        help="Run all available configs")
    parser.add_argument("--config", action="append", default=None,
                        help="Specific config(s) to run, e.g. --config BTC:15m")
    parser.add_argument("--fast", action="store_true", default=False,
                        help="Use 180d cache, skip 365d download")
    parser.add_argument("--allow-dirty", action="store_true", default=False,
                        help="Skip git tree clean check (for testing)")
    args, _ = parser.parse_known_args()

    # If --full is given, override to full mode (not implemented, just a placeholder)
    # If --config is given, use those configs
    # Otherwise default to --quick
    quick_mode = not args.full
    config_labels = _parse_config_labels(args.config)
    if config_labels:
        quick_mode = False  # custom mode

    try:
        operator_run(quick_mode=quick_mode, config_labels=config_labels, fast_daily=args.fast, allow_dirty=args.allow_dirty)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n  OPERATOR ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
