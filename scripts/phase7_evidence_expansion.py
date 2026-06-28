"""Phase 7 — Evidence expansion across symbols and timeframes.

Tests the frozen configuration (regime gate, atr14_20, immediate entry,
consecutive_loss_6) across multiple symbols and timeframes.

Assigns final rating:
  ROBUST_EDGE           — all gates pass
  REGIME_SPECIFIC_EDGE  — works in specific regimes only
  INSUFFICIENT_TRADES   — <100 total OOS trades
  OVERFIT_SUSPECTED     — single window/symbol >50% of profit
  NO_EDGE               — EV<=0 or PF<=1.5 or DD>=12
"""

import json, os, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.forward_test_runner import run_forward_test
from production_replay.kill_switch import check_kill_switch

RISK_CFG = {"consecutive_loss_cap": {"max_losses": 6}}
RESULTS_DIR = "phase7_results"

TEST_MATRIX = [
    # BTC across timeframes
    ("BTCUSDT", "15m", "BTC 15m (baseline)"),
    ("BTCUSDT", "5m",  "BTC 5m"),
    ("BTCUSDT", "30m", "BTC 30m"),
    ("BTCUSDT", "1h",  "BTC 1h"),
    # Major alts 15m
    ("ETHUSDT", "15m", "ETH 15m"),
    ("SOLUSDT", "15m", "SOL 15m"),
    ("BNBUSDT", "15m", "BNB 15m"),
    ("XRPUSDT", "15m", "XRP 15m"),
]


def run_one(symbol, timeframe, label):
    """Run forward test for one symbol/timeframe. Returns results dict."""
    out_dir = os.path.join(RESULTS_DIR, f"{symbol}_{timeframe}")
    os.makedirs(out_dir, exist_ok=True)

    r = run_forward_test(
        symbol=symbol, timeframe=timeframe, data_days=365,
        dry_run=False, output_dir=out_dir,
        risk_controls=RISK_CFG,
    )

    trades = r.get("trade_diagnostics", [])
    win_count = sum(1 for t in trades if t["net_r"] > 0)
    wr = 100 * win_count / len(trades) if trades else 0
    ev = sum(t["net_r"] for t in trades) / len(trades) if trades else 0
    wpnl = sum(t["net_r"] for t in trades if t["net_r"] > 0)
    lpnl = abs(sum(t["net_r"] for t in trades if t["net_r"] <= 0))
    pf = wpnl / lpnl if lpnl > 0 else (wpnl if wpnl > 0 else 0)

    cons = 0; max_cons = 0
    for t in trades:
        if t["net_r"] <= 0: cons += 1; max_cons = max(max_cons, cons)
        else: cons = 0

    cum = 0.0; peak = 0.0; dd = 0.0
    for t in trades:
        cum += t["net_r"]
        peak = max(peak, cum)
        dd = max(dd, peak - cum)

    kill = check_kill_switch(trades=trades)

    # Per-window contribution
    window_pnl = defaultdict(float)
    for t in trades:
        w = t.get("window", "unknown")
        window_pnl[w] += t["net_r"]
    total_pnl = sum(t["net_r"] for t in trades)
    max_window_pct = max((pnl / total_pnl * 100) for pnl in window_pnl.values()) if total_pnl > 0 else 0

    result = {
        "label": label,
        "symbol": symbol,
        "timeframe": timeframe,
        "windows": r.get("windows", 0),
        "trades": len(trades),
        "wr": round(wr, 1),
        "ev": round(ev, 3),
        "pf": round(pf, 2),
        "cumulative_dd_r": round(dd, 2),
        "max_consecutive_losses": max_cons,
        "kill_triggered": kill["kill_triggered"],
        "max_window_pnl_pct": round(max_window_pct, 1),
        "window_count": len(window_pnl),
        "total_pnl": round(total_pnl, 2),
        "per_window_pnl": {k: round(v, 2) for k, v in sorted(window_pnl.items())},
    }
    return result


def aggregate_results(all_results):
    """Aggregate across all symbols/timeframes and assign rating."""
    print("\n" + "=" * 100)
    print("  PHASE 7 — EVIDENCE EXPANSION REPORT")
    print("=" * 100)

    header = f"{'Config':<25s} {'Windows':>7s} {'Trades':>6s} {'WR%':>5s} {'EV(R)':>8s} {'PF':>6s} {'DD(R)':>7s} {'MaxCons':>7s} {'Kill':>5s} {'MaxWin%':>7s}"
    print(f"\n{header}")
    print("-" * 100)

    total_trades_all = 0
    total_pnl_all = 0.0
    all_trades_list = []
    all_ev = []
    all_pf = []
    all_dd = []
    kills = 0
    windows_with_data = 0

    for r in all_results:
        label = r["label"]
        line = f"{label:<25s} {r['window_count']:>7d} {r['trades']:>6d} {r['wr']:>5.1f} {r['ev']:+>8.3f} {r['pf']:>6.2f} {r['cumulative_dd_r']:>7.2f} {r['max_consecutive_losses']:>7d} {'KILL' if r['kill_triggered'] else 'OK':>5s} {r['max_window_pnl_pct']:>6.1f}%"
        if r["trades"] == 0:
            line += "  [NO TRADES]"
        print(line)

        total_trades_all += r["trades"]
        total_pnl_all += r["total_pnl"]
        all_ev.append(r["ev"])
        all_pf.append(r["pf"])
        all_dd.append(r["cumulative_dd_r"])
        if r["kill_triggered"]:
            kills += 1
        windows_with_data += r["window_count"]

    # Combined across all configs
    all_pnls = []
    for r in all_results:
        all_pnls.extend(r.get("per_window_pnl", {}).values())
    max_config_pnl = max(r["total_pnl"] for r in all_results) if all_results else 0
    total_pnl = sum(r["total_pnl"] for r in all_results)
    max_config_pct = (max_config_pnl / total_pnl * 100) if total_pnl > 0 else 0

    print("-" * 100)
    print(f"{'TOTAL':<25s} {windows_with_data:>7d} {total_trades_all:>6d} {'':>5s} {'':>8s} {'':>6s} {'':>7s} {'':>7s} {'':>5s} {'':>7s}")
    print()

    # --- Gates ---
    print("=" * 100)
    print("  ACCEPTANCE GATES")
    print("=" * 100)

    non_zero = [r for r in all_results if r["trades"] > 0]

    gate_trades = total_trades_all >= 100
    gate_dd = all(r["cumulative_dd_r"] < 12.0 for r in non_zero)
    gate_dd_pref = all(r["cumulative_dd_r"] < 8.0 for r in non_zero)
    gate_ev = all(r["ev"] > 0 for r in non_zero)
    gate_pf = all(r["pf"] > 1.5 for r in non_zero)
    gate_kill = all(not r["kill_triggered"] for r in all_results)
    gate_concentration = max_config_pct < 50.0

    gates = {
        "total_trades >= 100": (gate_trades, f"{total_trades_all}"),
        "cumulative DD < 12.0R": (gate_dd, ", ".join(f"{r['label']}: {r['cumulative_dd_r']:.1f}R" for r in non_zero)),
        "cumulative DD < 8.0R (preferred)": (gate_dd_pref, ""),
        "EV > 0 (all configs)": (gate_ev, ", ".join(f"{r['label']}: {r['ev']:+.3f}R" for r in non_zero)),
        "PF > 1.5 (all configs)": (gate_pf, ", ".join(f"{r['label']}: {r['pf']:.2f}" for r in non_zero)),
        "kill switch not triggered": (gate_kill, f"{kills} kill(s)"),
        "no config > 50% profit": (gate_concentration, f"max {max_config_pct:.1f}% from {max([r['label'] for r in all_results if r['total_pnl'] == max_config_pnl], default='?')}"),
    }

    all_pass = True
    for name, (passed, detail) in gates.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {status:4s} | {name:<40s} {detail}")

    print()
    meaningful = [r for r in all_results if r["trades"] >= 10]
    no_edge_configs = [r for r in meaningful if r["ev"] <= 0 or r["pf"] <= 1.5 or r["cumulative_dd_r"] >= 12.0]
    valid_configs = [r for r in meaningful if r["ev"] > 0 and r["pf"] > 1.5 and r["cumulative_dd_r"] < 12.0 and not r["kill_triggered"]]
    zero_trade_configs = [r for r in all_results if r["trades"] == 0]

    # --- Rating ---
    print("=" * 100)
    print("  RATING")
    print("=" * 100)

    if total_trades_all < 100:
        rating = "INSUFFICIENT_TRADES"
        reason = f"only {total_trades_all} total OOS trades across all configs"
    elif meaningful and not no_edge_configs and max_config_pct < 50 and gate_kill and all_pass:
        if gate_dd_pref:
            rating = "ROBUST_EDGE"
            reason = "all gates pass, DD under 8R preferred threshold"
        else:
            rating = "ROBUST_EDGE"
            reason = "all gates pass"
    elif valid_configs and no_edge_configs:
        rating = "REGIME_SPECIFIC_EDGE"
        valid_names = ", ".join(r["label"] for r in valid_configs)
        fail_names = ", ".join(r["label"] for r in no_edge_configs)
        reason = f"edge confirmed for {valid_names}; fails for {fail_names}"
    elif valid_configs and not no_edge_configs:
        rating = "REGIME_SPECIFIC_EDGE"
        valid_names = ", ".join(r["label"] for r in valid_configs)
        zero_names = ", ".join(r["label"] for r in zero_trade_configs)
        reason = f"edge confirmed for {valid_names}; no data for {zero_names}" if zero_names else f"limited to {valid_names}"
    elif not gate_kill:
        rating = "NO_EDGE"
        reason = "kill switch triggered"
    elif no_edge_configs:
        rating = "NO_EDGE"
        names = ", ".join(r["label"] for r in no_edge_configs)
        reason = f"all configs fail edge criteria: {names}"
    elif max_config_pct >= 50.0:
        rating = "OVERFIT_SUSPECTED"
        reason = f"single config contributes {max_config_pct:.0f}% of total profit"
    else:
        rating = "REGIME_SPECIFIC_EDGE"
        reason = "mixed results across configs"

    print(f"\n  Rating: {rating}")
    print(f"  Reason: {reason}\n")

    report = {
        "rating": rating,
        "reason": reason,
        "gates": {k: v[0] for k, v in gates.items()},
        "results": all_results,
        "summary": {
            "total_trades": total_trades_all,
            "total_pnl_r": round(total_pnl_all, 2),
            "configs_with_trades": len(non_zero),
            "configs_zero_trades": len(zero_trade_configs),
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    path = os.path.join(RESULTS_DIR, "phase7_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"[SAVED] {path}")

    return report


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_results = []

    print("=" * 100)
    print("  PHASE 7 — EVIDENCE EXPANSION")
    print(f"  Config: atr14_20, immediate entry, regime gate, consec_loss_6")
    print(f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    for symbol, timeframe, label in TEST_MATRIX:
        print(f"\n[{label}] Running forward test...")
        t0 = time.time()
        try:
            result = run_one(symbol, timeframe, label)
            elapsed = time.time() - t0
            print(f"  -> {result['trades']} trades, {result['windows']} windows, EV {result['ev']:+.3f}R, DD {result['cumulative_dd_r']:.2f}R ({elapsed:.0f}s)")
            all_results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({
                "label": label, "symbol": symbol, "timeframe": timeframe,
                "error": str(e), "trades": 0, "windows": 0,
                "wr": 0, "ev": 0, "pf": 0, "cumulative_dd_r": 0,
                "max_consecutive_losses": 0, "kill_triggered": False,
                "max_window_pnl_pct": 0, "window_count": 0,
                "total_pnl": 0, "per_window_pnl": {},
            })

    report = aggregate_results(all_results)
    return report


if __name__ == "__main__":
    main()
