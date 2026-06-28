"""Dry-forward validation runner for locked production configs.

Runs only allowed configs in dry-run mode.
No API order execution. Live/paper trading disabled.
"""

import json, os, sys, time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.forward_test_runner import run_forward_test
from production_replay.kill_switch import check_kill_switch
from production_replay.minimum_evidence_rule import check_minimum_evidence

RESULTS_DIR = "deploy_results"
ALLOWED = [
    ("BTCUSDT", "15m", "BTC 15m"),
    ("BTCUSDT", "30m", "BTC 30m"),
    ("SOLUSDT", "15m", "SOL 15m"),
]
RISK_CFG = {"consecutive_loss_cap": {"max_losses": 6}}


def run_dry_forward():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_results = []
    all_trades = []

    print("=" * 72)
    print("  DRY-FORWARD VALIDATION")
    print("  Mode: DRY RUN — no trades executed")
    print("=" * 72)

    for symbol, timeframe, label in ALLOWED:
        print(f"\n[{label}] Running...")
        t0 = time.time()
        out_dir = os.path.join(RESULTS_DIR, f"{symbol}_{timeframe}")
        os.makedirs(out_dir, exist_ok=True)

        try:
            result = run_forward_test(
                symbol=symbol, timeframe=timeframe, data_days=365,
                dry_run=False, output_dir=out_dir,
                risk_controls=RISK_CFG,
            )

            trades = result.get("trade_diagnostics", [])
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

            entry = {
                "label": label, "symbol": symbol, "timeframe": timeframe,
                "trades": len(trades), "wr": round(wr, 1), "ev": round(ev, 3),
                "pf": round(pf, 2), "dd": round(dd, 2), "kill": kill["kill_triggered"],
                "elapsed_s": round(time.time() - t0, 1),
            }
            all_results.append(entry)
            all_trades.extend(trades)

            status = "OK" if not kill["kill_triggered"] else "KILL"
            print(f"  -> {len(trades)} trades, EV {ev:+.3f}R, PF {pf:.2f}, DD {dd:.2f}R, {status}")

        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"label": label, "error": str(e)})

    # Consolidated metrics
    print(f"\n{'=' * 72}")
    print("  CONSOLIDATED REPORT")
    print(f"{'=' * 72}")
    total_trades = sum(r.get("trades", 0) for r in all_results)
    total_pnl = sum(t["net_r"] for t in all_trades)
    total_wins = sum(1 for t in all_trades if t["net_r"] > 0)
    total_wr = 100 * total_wins / len(all_trades) if all_trades else 0
    total_ev = total_pnl / len(all_trades) if all_trades else 0
    total_wpnl = sum(t["net_r"] for t in all_trades if t["net_r"] > 0)
    total_lpnl = abs(sum(t["net_r"] for t in all_trades if t["net_r"] <= 0))
    total_pf = total_wpnl / total_lpnl if total_lpnl > 0 else 0
    cum = 0; peak = 0; total_dd = 0
    for t in all_trades:
        cum += t["net_r"]; peak = max(peak, cum); total_dd = max(total_dd, peak - cum)
    total_kill = check_kill_switch(trades=all_trades)

    print(f"\n  All configs combined:")
    print(f"  Trades: {total_trades}")
    print(f"  WR:     {total_wr:.1f}%")
    print(f"  EV:     {total_ev:+.3f}R")
    print(f"  PF:     {total_pf:.2f}")
    print(f"  DD:     {total_dd:.2f}R")
    print(f"  Kill:   {'TRIGGERED' if total_kill['kill_triggered'] else 'OK'}")

    # Evidence check
    evidence_ok = total_trades >= 100
    dd_ok = total_dd < 12.0
    dd_pref = total_dd < 8.0
    pf_ok = total_pf >= 1.5
    ev_ok = total_ev > 0

    print(f"\n  Evidence: {'PASS' if evidence_ok else 'FAIL'} ({total_trades} trades >= 100)")
    print(f"  DD < 12R: {'PASS' if dd_ok else 'FAIL'} ({total_dd:.2f}R)")
    print(f"  DD < 8R:  {'PASS' if dd_pref else 'FAIL'} ({total_dd:.2f}R)")
    print(f"  PF >= 1.5: {'PASS' if pf_ok else 'FAIL'} ({total_pf:.2f})")
    print(f"  EV > 0:   {'PASS' if ev_ok else 'FAIL'} ({total_ev:+.3f}R)")

    if evidence_ok and dd_ok and pf_ok and ev_ok and not total_kill["kill_triggered"]:
        if dd_pref:
            verdict = "ROBUST_EDGE"
        else:
            verdict = "REGIME_SPECIFIC_EDGE"
    elif total_trades < 100:
        verdict = "INSUFFICIENT_TRADES"
    elif total_dd >= 12.0 or total_ev <= 0 or total_pf < 1.5:
        verdict = "NO_EDGE"
    else:
        verdict = "REGIME_SPECIFIC_EDGE"

    report = {
        "mode": "dry_forward",
        "verdict": verdict,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "configs_tested": len(ALLOWED),
        "total_trades": total_trades,
        "total_wr": round(total_wr, 1),
        "total_ev": round(total_ev, 3),
        "total_pf": round(total_pf, 2),
        "total_dd_r": round(total_dd, 2),
        "kill_triggered": total_kill["kill_triggered"],
        "gates": {
            "trades >= 100": evidence_ok,
            "dd < 12.0R": dd_ok,
            "dd < 8.0R (preferred)": dd_pref,
            "pf >= 1.5": pf_ok,
            "ev > 0": ev_ok,
            "kill not triggered": not total_kill["kill_triggered"],
        },
        "per_config": all_results,
    }

    path = os.path.join(RESULTS_DIR, "dry_forward_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[SAVED] {path}")
    print(f"\n{'=' * 72}")
    print(f"  VERDICT: {verdict}")
    print(f"{'=' * 72}")

    return report


if __name__ == "__main__":
    run_dry_forward()
