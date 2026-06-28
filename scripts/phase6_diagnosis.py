"""Phase 6 — Cumulative drawdown diagnosis.

Analyzes Phase 5 forward-test trades to find where cumulative DD builds.
No strategy changes — diagnosis only.
"""

import json, csv, os, sys
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def load_trades():
    """Load and normalize trades from either JSON or CSV format."""
    try:
        with open("phase5_results/forward_test_result.json") as f:
            raw = json.load(f)["trade_diagnostics"]
    except (FileNotFoundError, KeyError):
        raw = []
        with open("phase5_results/daily_report.csv", newline="") as f:
            for row in csv.DictReader(f):
                raw.append(row)

    # Normalize field names
    trades = []
    for t in raw:
        trades.append({
            "date": t.get("date", t.get("timestamp", "unknown")),
            "direction": t["direction"],
            "net_r": float(t["net_r"]),
            "exit_reason": t["exit_reason"],
            "holding_candles": int(t.get("holding_candles", 0)),
            "window": t.get("window", ""),
            "entry_price": float(t.get("entry_price", 0)),
            "exit_price": float(t.get("exit_price", 0)),
        })
    return trades


def compute_equity_curve(trades):
    """Compute cumulative equity curve."""
    curve = []
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for t in trades:
        r = t["net_r"]
        cum += r
        peak = max(peak, cum)
        dd = peak - cum
        curve.append({"cum": round(cum, 2), "peak": round(peak, 2), "dd": round(dd, 2)})
    return curve


def pct(a, b):
    if b == 0:
        return 0
    return round(100 * a / b)


def analyze_dd_sources(trades):
    """Analyze where DD comes from."""
    curve = compute_equity_curve(trades)

    max_dd_idx = max(range(len(curve)), key=lambda i: curve[i]["dd"])
    max_dd = curve[max_dd_idx]["dd"]
    peak_before_dd = curve[max_dd_idx]["peak"]
    cum_at_max_dd = curve[max_dd_idx]["cum"]

    print("=" * 72)
    print("  PHASE 6 - CUMULATIVE DRAWDOWN DIAGNOSIS")
    print("=" * 72)

    print(f"\nTotal trades:        {len(trades)}")
    print(f"Cumulative PnL:      {curve[-1]['cum']:.2f}R")
    print(f"Max peak:            {peak_before_dd:.2f}R")
    print(f"Max drawdown:        {max_dd:.2f}R")
    print(f"Trough at trade:     #{max_dd_idx + 1}")
    print(f"Peak before trough:  {peak_before_dd:.2f}R")
    print(f"Trough value:        {cum_at_max_dd:.2f}R")

    # --- Window-level breakdown ---
    print(f"\n--- WINDOW ANALYSIS ---")
    wins = defaultdict(list)
    for t in trades:
        wins[t["window"]].append(t)

    prev_cum = 0.0
    global_peak = 0.0
    for wname, wtrades in sorted(wins.items()):
        w_pnl = sum(t["net_r"] for t in wtrades)
        w_wins = sum(1 for t in wtrades if t["net_r"] > 0)
        w_dd = max(compute_equity_curve(wtrades), key=lambda c: c["dd"])["dd"]
        w_cons = 0
        w_max_cons = 0
        for t in wtrades:
            if t["net_r"] <= 0:
                w_cons += 1
                w_max_cons = max(w_max_cons, w_cons)
            else:
                w_cons = 0
        start_cum = prev_cum
        end_cum = prev_cum + w_pnl
        prev_cum = end_cum
        global_peak = max(global_peak, end_cum)

        print(f"\n  Window: {wname}")
        print(f"    Trades: {len(wtrades)}  WR: {w_wins}/{len(wtrades)} = {pct(w_wins, len(wtrades))}%")
        print(f"    PnL:    {w_pnl:+.2f}R  (start {start_cum:.1f}R -> end {end_cum:.1f}R)")
        print(f"    In-window DD: {w_dd:.2f}R")
        print(f"    Max cons losses: {w_max_cons}")

    # --- Direction clustering ---
    print(f"\n--- DIRECTION ANALYSIS ---")
    for direction in ["LONG", "SHORT"]:
        d_trades = [t for t in trades if t["direction"] == direction]
        if not d_trades:
            continue
        d_pnl = sum(t["net_r"] for t in d_trades)
        d_wins = sum(1 for t in d_trades if t["net_r"] > 0)
        d_losses = len(d_trades) - d_wins
        print(f"\n  {direction}: {len(d_trades)} trades, {d_wins}W/{d_losses}L, PnL {d_pnl:+.2f}R, WR {pct(d_wins, len(d_trades))}%")

        cons = 0
        max_cons_dir = 0
        for t in d_trades:
            if t["net_r"] <= 0:
                cons += 1
                max_cons_dir = max(max_cons_dir, cons)
            else:
                cons = 0
        print(f"    Max consecutive losses: {max_cons_dir}")

    # --- Consecutive loss analysis ---
    print(f"\n--- CONSECUTIVE LOSS CLUSTERS ---")
    cons = 0
    cluster_start = 0
    clusters = []
    for i, t in enumerate(trades):
        if t["net_r"] <= 0:
            if cons == 0:
                cluster_start = i
            cons += 1
        else:
            if cons >= 3:
                cluster_pnl = sum(trades[j]["net_r"] for j in range(cluster_start, i))
                cluster_dir = [trades[j]["direction"] for j in range(cluster_start, i)]
                same = all(d == cluster_dir[0] for d in cluster_dir)
                clusters.append({
                    "count": cons,
                    "pnl": cluster_pnl,
                    "all_same_dir": same,
                    "direction": cluster_dir[0] if same else "mixed",
                    "dates": f"{trades[cluster_start]['date'][:10]} to {trades[i-1]['date'][:10]}",
                })
            cons = 0
    if cons >= 3:
        cluster_pnl = sum(trades[j]["net_r"] for j in range(cluster_start, len(trades)))
        clusters.append({
            "count": cons,
            "pnl": cluster_pnl,
            "all_same_dir": True,
            "direction": trades[cluster_start]["direction"],
            "dates": f"{trades[cluster_start]['date'][:10]} to {trades[-1]['date'][:10]}",
        })

    for c in clusters:
        print(f"\n  {c['count']} consec losses, {c['pnl']:.2f}R, all {c['direction']}:  {c['dates']}")

    # --- Max DD contributors ---
    print(f"\n--- MAX DRAWDOWN CONTRIBUTORS ---")
    peak_idx = max(range(max_dd_idx + 1), key=lambda i: curve[i]["cum"])
    print(f"\n  Peak trade #{peak_idx + 1}: cum={curve[peak_idx]['cum']:.2f}R on {trades[peak_idx]['date'][:10]}")
    print(f"  Trough trade #{max_dd_idx + 1}: cum={curve[max_dd_idx]['cum']:.2f}R on {trades[max_dd_idx]['date'][:10]}")
    dd_trades = trades[peak_idx + 1:max_dd_idx + 1]
    print(f"\n  Trades contributing to max DD ({len(dd_trades)} trades):")
    for t in dd_trades:
        print(f"    {t['date'][:10]}  {t['direction']:6s}  {t['net_r']:+7.2f}R  {t['exit_reason']:12s}  ({t['window'][:17]}...)")
    dd_losses = sum(1 for t in dd_trades if t["net_r"] <= 0)
    dd_wins = sum(1 for t in dd_trades if t["net_r"] > 0)
    dd_pnl = sum(t["net_r"] for t in dd_trades)
    print(f"    -> {dd_wins}W/{dd_losses}L, PnL {dd_pnl:+.2f}R")

    # --- Post-loss behavior ---
    print(f"\n--- POST-LOSS BEHAVIOR ---")
    post_loss_wins = 0
    post_loss_losses = 0
    post_loss_same_dir = 0
    post_loss_total = 0
    for i in range(len(trades) - 1):
        if trades[i]["net_r"] <= 0:
            post_loss_total += 1
            next_t = trades[i + 1]
            if next_t["net_r"] > 0:
                post_loss_wins += 1
            else:
                post_loss_losses += 1
            if next_t["direction"] == trades[i]["direction"]:
                post_loss_same_dir += 1
    print(f"\n  After a loss, next trade wins: {post_loss_wins}/{post_loss_total} = {pct(post_loss_wins, post_loss_total)}%")
    print(f"  After a loss, next trade also loses: {post_loss_losses}/{post_loss_total} = {pct(post_loss_losses, post_loss_total)}%")
    print(f"  After a loss, same direction: {post_loss_same_dir}/{post_loss_total} = {pct(post_loss_same_dir, post_loss_total)}%")

    # --- Exit reason breakdown ---
    print(f"\n--- EXIT REASON ANALYSIS ---")
    reasons = defaultdict(list)
    for t in trades:
        reasons[t["exit_reason"]].append(t)
    for reason, rtrades in sorted(reasons.items()):
        r_pnl = sum(t["net_r"] for t in rtrades)
        r_wins = sum(1 for t in rtrades if t["net_r"] > 0)
        print(f"  {reason:12s}: {len(rtrades):2d} trades, WR {pct(r_wins, len(rtrades)):2d}%, PnL {r_pnl:+7.2f}R")

    # --- Summary ---
    print(f"\n{'=' * 72}")
    print("  DIAGNOSIS SUMMARY")
    print(f"{'=' * 72}")
    print(f"\n1. Cumulative DD = {max_dd:.2f}R, formed across windows:")
    for c in clusters:
        print(f"   - {c['count']} consec losses ({c['direction']}): {c['dates']} ({c['pnl']:.1f}R)")
    print(f"\n2. Post-loss: {pct(post_loss_same_dir, post_loss_total)}% same-direction, {pct(post_loss_losses, post_loss_total)}% repeat loss")
    print(f"\n3. Recommended risk controls to test:")
    print(f"   a) Post-loss cooldown: skip N candles after a loss")
    print(f"   b) Consecutive loss cap: skip rest of session after N losses in a row")
    print(f"   c) Daily loss cap: stop trading after losing M R in a day")
    print(f"   d) Direction cooldown after losing trade")
    print(f"   e) Rolling drawdown throttle: reduce or stop when in drawdown")
    print(f"   f) Max trades per window to limit exposure in bad regimes")

    return {"max_dd": max_dd, "clusters": clusters}


if __name__ == "__main__":
    trades = load_trades()
    if not trades:
        print("ERROR: no trades loaded")
        sys.exit(1)
    analyze_dd_sources(trades)
