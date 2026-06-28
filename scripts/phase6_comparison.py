"""Phase 6 — Risk control comparison.

Runs each control individually and in combination, reports metrics.
"""

import json, os, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.forward_test_runner import run_forward_test


CONTROLS_TO_TEST = {
    "baseline": None,
    "post_loss_cooldown_3": {"post_loss_cooldown": {"min_candles": 3}},
    "post_loss_cooldown_5": {"post_loss_cooldown": {"min_candles": 5}},
    "direction_cooldown_5": {"direction_cooldown": {"min_candles": 5}},
    "direction_cooldown_10": {"direction_cooldown": {"min_candles": 10}},
    "consec_loss_cap_4": {"consecutive_loss_cap": {"max_losses": 4}},
    "consec_loss_cap_3": {"consecutive_loss_cap": {"max_losses": 3}},
    "daily_loss_cap_3r": {"daily_loss_cap": {"max_daily_loss_r": 3.0}},
    "daily_loss_cap_2r": {"daily_loss_cap": {"max_daily_loss_r": 2.0}},
    "rolling_dd_8r": {"rolling_drawdown": {"max_dd_r": 8.0}},
    "rolling_dd_10r": {"rolling_drawdown": {"max_dd_r": 10.0}},
    "max_trades_20": {"max_trades_per_window": {"max_trades": 20}},
    "max_trades_25": {"max_trades_per_window": {"max_trades": 25}},
    "combo": {
        "post_loss_cooldown": {"min_candles": 3},
        "direction_cooldown": {"min_candles": 5},
        "consecutive_loss_cap": {"max_losses": 4},
        "daily_loss_cap": {"max_daily_loss_r": 3.0},
    },
    "combo_aggressive": {
        "post_loss_cooldown": {"min_candles": 5},
        "direction_cooldown": {"min_candles": 10},
        "consecutive_loss_cap": {"max_losses": 3},
        "daily_loss_cap": {"max_daily_loss_r": 2.0},
        "rolling_drawdown": {"max_dd_r": 8.0},
    },
}


def compute_cum_dd(trades):
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for t in trades:
        cum += float(t["net_r"])
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return round(dd, 2)


def compute_max_cons_losses(trades):
    max_cons = 0
    cons = 0
    for t in trades:
        if float(t["net_r"]) <= 0:
            cons += 1
            max_cons = max(max_cons, cons)
        else:
            cons = 0
    return max_cons


def run_comparison():
    results = {}
    print("=" * 110)
    print(f"  PHASE 6 — RISK CONTROL COMPARISON")
    print(f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 110)
    print(f"{'Control':<30s} {'Trades':>6s} {'WR%':>5s} {'EV(R)':>8s} {'PF':>6s} {'DD(R)':>7s} {'MaxCons':>7s} {'DBlocked':>8s} {'Kill':>5s}")
    print("-" * 110)

    for name, config in CONTROLS_TO_TEST.items():
        t0 = time.time()
        try:
            result = run_forward_test(dry_run=False, risk_controls=config)
            trades = result.get("trade_diagnostics", [])
            wm = result.get("window_metrics", [])
            win_count = sum(1 for t in trades if float(t["net_r"]) > 0)
            wr = 100 * win_count / len(trades) if trades else 0
            ev = sum(float(t["net_r"]) for t in trades) / len(trades) if trades else 0
            wins_pnl = sum(float(t["net_r"]) for t in trades if float(t["net_r"]) > 0)
            losses_pnl = abs(sum(float(t["net_r"]) for t in trades if float(t["net_r"]) <= 0))
            pf = wins_pnl / losses_pnl if losses_pnl > 0 else (wins_pnl if wins_pnl > 0 else 0)
            cum_dd = compute_cum_dd(trades)
            max_cons = compute_max_cons_losses(trades)
            rc_rejected = sum(m.get("rc_rejected", 0) for m in wm)
            kill_triggered = cum_dd >= 12.0
        except Exception as e:
            print(f"{name:<30s} ERROR: {e}")
            results[name] = {"error": str(e)}
            continue

        elapsed = time.time() - t0
        results[name] = {
            "trades": len(trades),
            "wr": round(wr, 1),
            "ev": round(ev, 3),
            "pf": round(pf, 2),
            "cum_dd": cum_dd,
            "max_cons": max_cons,
            "rc_rejected": rc_rejected,
            "kill_triggered": kill_triggered,
        }
        kill_mark = "KILL" if kill_triggered else "OK"
        print(f"{name:<30s} {len(trades):>6d} {wr:>5.1f} {ev:>+8.3f} {pf:>6.2f} {cum_dd:>7.2f} {max_cons:>7d} {rc_rejected:>8d} {kill_mark:>5s}  ({elapsed:.0f}s)")

    print("-" * 110)
    print()
    print_report(results)

    # Save results
    out = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}
    os.makedirs("phase6_results", exist_ok=True)
    with open("phase6_results/comparison.json", "w") as f:
        json.dump(out, f, indent=2)
    print("[SAVED] phase6_results/comparison.json")


def print_report(results):
    print("=" * 110)
    print("  SUMMARY")
    print("=" * 110)
    baseline = results.get("baseline", {})
    if not baseline or "error" in baseline:
        print("  ERROR: baseline not available")
        return

    print(f"\n  Baseline: {baseline['trades']} trades, WR {baseline['wr']}%, EV {baseline['ev']:+}R, PF {baseline['pf']}, DD {baseline['cum_dd']}R")
    print(f"\n  {'Control':<30s} {'Trades':>7s} {'WR':>5s} {'EV':>8s} {'PF':>6s} {'DD':>7s} {'ConsLoss':>8s} {'Blckd':>6s} {'Kill':>5s} {'Eligible':>8s}")
    print("-" * 110)

    eligible = []
    for name, r in sorted(results.items()):
        if name == "baseline" or "error" in r:
            continue
        dd_ok = r["cum_dd"] < 12.0
        dd_great = r["cum_dd"] < 8.0
        ev_ok = r["ev"] > 0
        pf_ok = r["pf"] > 1.5
        trades_ok = r["trades"] >= 50 or "(insufficient)" in name
        status = ""
        if not dd_ok:
            status = "DD>12"
        elif not ev_ok:
            status = "EV<=0"
        elif not pf_ok:
            status = "PF<=1.5"
        elif dd_great:
            status = "PREFERRED"
        else:
            status = "PASS"
        eligible.append((name, r, status))

        print(f"{name:<30s} {r['trades']:>7d} {r['wr']:>5.1f} {r['ev']:+>8.3f} {r['pf']:>6.2f} {r['cum_dd']:>7.2f} {r['max_cons']:>8d} {r['rc_rejected']:>6d} {'KILL' if r['kill_triggered'] else 'OK':>5s} {status:>8s}")

    print("-" * 110)
    print(f"\n  Eligible (DD<12R, EV>0, PF>1.5):")
    eligible_pass = [e for e in eligible if e[2] == "PASS" or e[2] == "PREFERRED"]
    if eligible_pass:
        for name, r, status in eligible_pass:
            print(f"    {name:<30s} DD={r['cum_dd']}R EV={r['ev']:+}R PF={r['pf']} Trades={r['trades']} {status}")
    else:
        print("    NONE — all controls still have DD >= 12R or EV <= 0 or PF <= 1.5")
        # Find closest
        best = min(eligible, key=lambda e: (e[1]['cum_dd'], -e[1]['ev']))
        print(f"    Closest: {best[0]} — DD={best[1]['cum_dd']}R EV={best[1]['ev']:+}R PF={best[1]['pf']}")


if __name__ == "__main__":
    run_comparison()
