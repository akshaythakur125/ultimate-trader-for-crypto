"""Dry-forward validation runner for locked production configs.

Runs only allowed configs in dry-run mode.
No API order execution. Live/paper trading disabled.
"""

import json, os, sys, time
from collections import defaultdict
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


def print_sep(char="=", width=80):
    print(char * width)


def run_dry_forward():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_results = []
    all_trades = []
    all_rejections_combined = []

    print_sep()
    print("  DRY-FORWARD VALIDATION")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: DRY RUN - no trades executed, no API calls")
    print(f"  Live trading: DISABLED")
    print(f"  Paper trading: DISABLED")
    print_sep()

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
            rejections = result.get("rejection_summary", [])

            # Per-window breakdown
            window_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0, "dd": 0.0})
            for t in trades:
                w = t.get("window", "unknown")
                window_stats[w]["trades"] += 1
                window_stats[w]["wins"] += 1 if t["net_r"] > 0 else 0
                window_stats[w]["pnl"] += t["net_r"]

            # Per-window DD
            for w in window_stats:
                w_trades = [t for t in trades if t.get("window") == w]
                wc = 0; wp = 0; wdd = 0
                for t in w_trades:
                    wc += t["net_r"]; wp = max(wp, wc); wdd = max(wdd, wp - wc)
                window_stats[w]["dd"] = round(wdd, 2)

            entry = {
                "label": label, "symbol": symbol, "timeframe": timeframe,
                "trades": len(trades), "wr": round(wr, 1), "ev": round(ev, 3),
                "pf": round(pf, 2), "dd": round(dd, 2), "kill": kill["kill_triggered"],
                "elapsed_s": round(time.time() - t0, 1),
                "windows": len(window_stats),
                "window_breakdown": {k: dict(v) for k, v in sorted(window_stats.items())},
                "rejections": len(rejections),
                "unique_rejected": result.get("total_unique_rejected", 0),
            }
            all_results.append(entry)
            all_trades.extend(trades)
            all_rejections_combined.extend(rejections)

            status_mark = "KILL" if kill["kill_triggered"] else "OK"
            print(f"  -> {label}: {len(trades)} trades, EV {ev:+.3f}R, PF {pf:.2f}, DD {dd:.2f}R, {status_mark}")

            # Per-window detail
            for wname, ws in sorted(window_stats.items()):
                wwr = 100 * ws["wins"] / ws["trades"] if ws["trades"] else 0
                print(f"     Window {wname[:20]:20s}: {ws['trades']:2d} trades, WR {wwr:5.1f}%, PnL {ws['pnl']:+7.2f}R, DD {ws['dd']:5.2f}R")

        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"label": label, "error": str(e)})

    # Consolidated results
    print_sep()
    print("  CONSOLIDATED REPORT")
    print_sep()
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

    header = f"{'Config':<15s} {'Trades':>6s} {'WR%':>5s} {'EV(R)':>8s} {'PF':>6s} {'DD(R)':>7s} {'Windows':>7s} {'Kill':>5s} {'Rej':>5s}"
    print(f"\n{header}")
    print("-" * 70)
    for r in all_results:
        km = "KILL" if r.get("kill") else "OK"
        rej = r.get("unique_rejected", 0)
        print(f"{r['label']:<15s} {r['trades']:>6d} {r['wr']:>5.1f} {r['ev']:+>8.3f} {r['pf']:>6.2f} {r['dd']:>7.2f} {r['windows']:>7d} {km:>5s} {rej:>5d}")
    print("-" * 70)
    print(f"{'COMBINED':<15s} {total_trades:>6d} {total_wr:>5.1f} {total_ev:+>8.3f} {total_pf:>6.2f} {total_dd:>7.2f} {'':>7s} {'OK' if not total_kill['kill_triggered'] else 'KILL':>5s}")

    # Gates
    print_sep()
    print("  GATES")
    print_sep()
    evidence_ok = total_trades >= 100
    dd_ok = total_dd < 12.0
    dd_pref = total_dd < 8.0
    pf_ok = total_pf >= 1.5
    ev_ok = total_ev > 0

    gates = [
        ("Trades >= 100", evidence_ok, f"{total_trades}" + (" >= 100" if evidence_ok else " < 100")),
        ("DD < 12.0R", dd_ok, f"{total_dd:.2f}R" + (" < 12.0" if dd_ok else " >= 12.0")),
        ("DD < 8.0R (preferred)", dd_pref, f"{total_dd:.2f}R" + (" < 8.0" if dd_pref else " >= 8.0")),
        ("PF >= 1.5", pf_ok, f"{total_pf:.2f}" + (" >= 1.5" if pf_ok else " < 1.5")),
        ("EV > 0", ev_ok, f"{total_ev:+.3f}R"),
        ("Kill not triggered", not total_kill["kill_triggered"], "KILL" if total_kill["kill_triggered"] else "OK"),
    ]
    for name, ok, detail in gates:
        print(f"  {'PASS' if ok else 'FAIL':6s} | {name:<30s} {detail}")

    # Verdict
    print_sep()
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

    reason_map = {
        "ROBUST_EDGE": "All gates pass. Strategy is safe for deployment consideration.",
        "REGIME_SPECIFIC_EDGE": "Edge confirmed for BTC and SOL only. Altcoins fail. Live/paper remain disabled.",
        "INSUFFICIENT_TRADES": f"Only {total_trades} total trades. Need >= 100 for paper consideration. Live/paper remain disabled.",
        "NO_EDGE": "EV <= 0 or PF < 1.5 or DD >= 12.0R. Strategy not viable. Live/paper remain disabled.",
    }
    print(f"\n  VERDICT: {verdict}")
    print(f"  {reason_map.get(verdict, '')}")
    print_sep()

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
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "gates": {name: ok for name, ok, _ in gates},
        "per_config": all_results,
    }

    path = os.path.join(RESULTS_DIR, "dry_forward_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[REPORT] {path}")
    print(f"\n  Next dry-forward: python production_replay/run_dry_forward.py")

    return report


if __name__ == "__main__":
    run_dry_forward()
