"""Accelerated Evidence Engine — research-only historical validation.

Evaluates symbol/timeframe candidates against strict acceptance gates.
No live or paper trading enabled. All results are research-only.

Core candidates: BTC 15m, BTC 30m, SOL 15m
Quarantine candidates: ETH 15m/30m, LINK 15m, AVAX 15m, DOGE 15m, XRP 15m, BNB 15m

Usage:
    python -m production_replay.accelerated_evidence
"""

import json, os, sys, time
from collections import defaultdict
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.forward_test_runner import run_forward_test
from production_replay.kill_switch import check_kill_switch

RESULTS_DIR = "deploy_results"
REPORT_JSON = os.path.join(RESULTS_DIR, "accelerated_evidence_report.json")
REPORT_TXT = os.path.join(RESULTS_DIR, "accelerated_evidence_report.txt")

RISK_CFG = {"consecutive_loss_cap": {"max_losses": 6}}

CORE = [
    ("BTCUSDT", "15m", "BTC 15m"),
    ("BTCUSDT", "30m", "BTC 30m"),
    ("SOLUSDT", "15m", "SOL 15m"),
]

QUARANTINE = [
    ("ETHUSDT", "15m", "ETH 15m"),
    ("ETHUSDT", "30m", "ETH 30m"),
    ("LINKUSDT", "15m", "LINK 15m"),
    ("AVAXUSDT", "15m", "AVAX 15m"),
    ("DOGEUSDT", "15m", "DOGE 15m"),
    ("XRPUSDT", "15m", "XRP 15m"),
    ("BNBUSDT", "15m", "BNB 15m"),
]

MIN_TRADES = 75
MIN_EV = 0.30
MIN_PF = 1.40
MAX_DD = 10.0
MAX_CONSECUTIVE_LOSSES = 6


def _max_consecutive_losses(trades: list[dict]) -> int:
    losses = 0
    max_losses = 0
    for t in trades:
        if t.get("net_r", 0) <= 0:
            losses += 1
            max_losses = max(max_losses, losses)
        else:
            losses = 0
    return max_losses


def _quick_loss_pct(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    losses = sum(1 for t in trades if t.get("net_r", 0) <= 0)
    return round(100 * losses / len(trades), 1)


def _evaluate_candidate(symbol: str, timeframe: str, label: str, tier: str) -> dict:
    print(f"\n  [{label}] Evaluating ({tier})...", flush=True)
    t0 = time.time()
    out_dir = os.path.join(RESULTS_DIR, f"accel_{symbol}_{timeframe}")
    os.makedirs(out_dir, exist_ok=True)

    try:
        result = run_forward_test(
            symbol=symbol, timeframe=timeframe,
            data_days=75, dry_run=False, output_dir=out_dir,
            risk_controls=RISK_CFG,
            fast_daily=True, vm_fast=True,
        )
    except Exception as e:
        print(f"  [{label}] ERROR: {e}", flush=True)
        return {
            "symbol": symbol, "timeframe": timeframe, "label": label, "tier": tier,
            "status": "ERROR", "trades": 0, "wr": 0, "ev": 0, "pf": 0,
            "max_dd": 0, "max_consecutive_losses": 0,
            "quick_loss_pct": 0, "kill_triggered": False,
            "elapsed_s": round(time.time() - t0, 1),
            "gate_results": {g: False for g in [
                "trades >= 75", "EV > +0.30R", "PF >= 1.40",
                "max DD <= 10R", "max_consecutive_losses <= 6", "kill not triggered",
            ]},
            "verdict": "FAIL",
        }

    trades = result.get("trade_diagnostics", [])
    wins = sum(1 for t in trades if t["net_r"] > 0)
    wr = 100 * wins / len(trades) if trades else 0
    ev = sum(t["net_r"] for t in trades) / len(trades) if trades else 0
    wpnl = sum(t["net_r"] for t in trades if t["net_r"] > 0)
    lpnl = abs(sum(t["net_r"] for t in trades if t["net_r"] <= 0))
    pf = wpnl / lpnl if lpnl > 0 else (wpnl if wpnl > 0 else 0)

    cum = 0; peak = 0; max_dd = 0
    for t in trades:
        cum += t["net_r"]; peak = max(peak, cum); max_dd = max(max_dd, peak - cum)

    kill = check_kill_switch(trades=trades)
    max_cons = _max_consecutive_losses(trades)
    ql_pct = _quick_loss_pct(trades)

    gate_results = {
        "trades >= 75": len(trades) >= MIN_TRADES,
        "EV > +0.30R": ev > MIN_EV,
        "PF >= 1.40": pf >= MIN_PF,
        "max DD <= 10R": max_dd <= MAX_DD,
        "max_consecutive_losses <= 6": max_cons <= MAX_CONSECUTIVE_LOSSES,
        "kill not triggered": not kill["kill_triggered"],
    }

    all_pass = all(gate_results.values())
    if tier == "quarantine":
        verdict = "QUARANTINE"
    elif all_pass:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    entry = {
        "symbol": symbol, "timeframe": timeframe, "label": label, "tier": tier,
        "status": "completed",
        "trades": len(trades), "wr": round(wr, 1), "ev": round(ev, 3),
        "pf": round(pf, 2), "max_dd": round(max_dd, 2),
        "max_consecutive_losses": max_cons,
        "quick_loss_pct": ql_pct,
        "kill_triggered": kill["kill_triggered"],
        "elapsed_s": round(time.time() - t0, 1),
        "gate_results": gate_results,
        "verdict": verdict,
    }

    status_line = "OK" if len(trades) > 0 else "NO TRADES"
    print(f"  -> {label}: {len(trades)} trades, EV {ev:+.3f}R, PF {pf:.2f}, "
          f"DD {max_dd:.2f}R, {verdict} ({entry['elapsed_s']:.1f}s)", flush=True)
    return entry


def _build_report(all_results: list[dict]) -> dict:
    passed = [r for r in all_results if r["verdict"] == "PASS"]
    failed = [r for r in all_results if r["verdict"] == "FAIL"]
    quarantined = [r for r in all_results if r["verdict"] == "QUARANTINE"]

    return {
        "mode": "accelerated_evidence",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "candidates": all_results,
        "summary": {
            "total_candidates": len(all_results),
            "passed": len(passed),
            "failed": len(failed),
            "quarantined": len(quarantined),
            "message": (
                "Research-only results. Live trading disabled. "
                "Paper trading disabled. Candidates are not tradable "
                "unless promoted through formal gates."
            ),
        },
    }


def _write_txt_report(report: dict):
    lines = [
        "=" * 72,
        "  ACCELERATED EVIDENCE REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 72,
        "",
        "  Research-only — no live or paper trading enabled.",
        "",
        "--- Summary ---",
        f"  Total candidates: {report['summary']['total_candidates']}",
        f"  Passed:           {report['summary']['passed']}",
        f"  Failed:           {report['summary']['failed']}",
        f"  Quarantined:      {report['summary']['quarantined']}",
        "",
        "--- Results ---",
    ]
    for c in report["candidates"]:
        gate_status = "PASS" if c["verdict"] == "PASS" else (
            "QUARANTINE" if c["verdict"] == "QUARANTINE" else "FAIL"
        )
        lines.append("")
        lines.append(f"  {c['label']:15s} ({c['tier']:10s}) — {gate_status}")
        if c["status"] == "ERROR":
            lines.append(f"    ERROR during evaluation")
            continue
        lines.append(f"    Trades: {c['trades']:3d}  WR: {c['wr']:5.1f}%  "
                     f"EV: {c['ev']:+7.3f}R  PF: {c['pf']:5.2f}")
        lines.append(f"    Max DD: {c['max_dd']:5.2f}R  Max Cons Losses: {c['max_consecutive_losses']:2d}  "
                     f"Quick Loss: {c['quick_loss_pct']:5.1f}%  Kill: {'YES' if c['kill_triggered'] else 'NO'}")
        lines.append(f"    Gates:")
        for gname, gpass in c["gate_results"].items():
            lines.append(f"      {'PASS' if gpass else 'FAIL'} | {gname}")

    lines.append("")
    lines.append("--- Gates (all must pass for PASS verdict) ---")
    lines.append(f"  trades >= {MIN_TRADES}")
    lines.append(f"  EV > +{MIN_EV}R")
    lines.append(f"  PF >= {MIN_PF}")
    lines.append(f"  max DD <= {MAX_DD}R")
    lines.append(f"  max consecutive losses <= {MAX_CONSECUTIVE_LOSSES}")
    lines.append(f"  kill not triggered")
    lines.append("")
    lines.append("--- Disclaimer ---")
    lines.append("  " + report["summary"]["message"])
    lines.append("")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 72)

    with open(REPORT_TXT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[TEXT REPORT] {REPORT_TXT}")


def run_accelerated_evidence() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    start = time.time()

    print("=" * 72)
    print("  ACCELERATED EVIDENCE ENGINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Research-only — no live or paper trading enabled.")
    print("=" * 72)

    print("\n  Core candidates:")
    for sym, tf, lab in CORE:
        print(f"    {lab:15s} ({sym}, {tf})")
    print("\n  Quarantine candidates:")
    for sym, tf, lab in QUARANTINE:
        print(f"    {lab:15s} ({sym}, {tf})")

    all_results: list[dict] = []

    print("\n" + "=" * 72)
    print("  Evaluating core candidates...")
    for symbol, timeframe, label in CORE:
        entry = _evaluate_candidate(symbol, timeframe, label, "core")
        all_results.append(entry)

    print("\n" + "=" * 72)
    print("  Evaluating quarantine candidates...")
    for symbol, timeframe, label in QUARANTINE:
        entry = _evaluate_candidate(symbol, timeframe, label, "quarantine")
        all_results.append(entry)

    report = _build_report(all_results)

    with open(REPORT_JSON, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[JSON REPORT] {REPORT_JSON}")

    _write_txt_report(report)

    elapsed = time.time() - start
    print(f"\n  {'='*60}")
    print(f"  ACCELERATED EVIDENCE COMPLETE")
    print(f"  Passed: {report['summary']['passed']}  "
          f"Failed: {report['summary']['failed']}  "
          f"Quarantined: {report['summary']['quarantined']}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Live trading: DISABLED  Paper trading: DISABLED")
    print(f"  {'='*60}")

    return report


if __name__ == "__main__":
    try:
        run_accelerated_evidence()
    except Exception as e:
        print(f"\n  ACCELERATED EVIDENCE ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
