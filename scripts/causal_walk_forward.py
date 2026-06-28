#!/usr/bin/env python3
"""Causal walk-forward regime validation — no future leakage.

Primary:  30d train, 30d test, 30d step (non-overlapping windows)
Secondary: 30d train, 30d test, 15d step (overlapping, deduplicated)
"""

import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(line_buffering=True)

from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab import FrozenConfig, WalkForwardReplay

frozen = FrozenConfig()
rcfg = ReplayConfig(warmup_candles=50, taker_fee_percent=0.04,
    slippage_percent=0.02, funding_per_candle_percent=0.001)

def dedup_trades(windows):
    """Return (raw_total, unique_count) from window trade timestamps."""
    raw = sum(w.test_trades for w in windows)
    all_ts = set()
    for w in windows:
        all_ts.update(w.test_trade_timestamps)
    return raw, len(all_ts)

def check_overlap(windows):
    """Check if any test windows overlap. Returns (overlap_found, description)."""
    if len(windows) < 2:
        return False, "single window"
    periods = [(w.test_start, w.test_end) for w in windows]
    for i in range(len(periods)):
        for j in range(i + 1, len(periods)):
            s1, e1 = periods[i]
            s2, e2 = periods[j]
            if s1 < e2 and s2 < e1:
                return True, f"window {i} ({s1}->{e1}) overlaps with window {j} ({s2}->{e2})"
    return False, "none"

def run_and_report(train_days, test_days, step, label):
    print(f"\n{'='*70}", flush=True)
    print(f"{label}")
    print(f"  train={train_days}d  test={test_days}d  step={step}d", flush=True)
    print(f"{'='*70}", flush=True)

    wf = WalkForwardReplay(frozen)
    t0 = time.time()
    wf.run(symbol="BTCUSDT", timeframe="15m",
           train_days=train_days, test_days=test_days,
           step=step, run_regime=True)
    elapsed = time.time() - t0

    a_windows = list(reversed(wf.windows))
    r_windows = list(reversed(wf.regime_windows))

    if not a_windows:
        print("  No windows formed.", flush=True)
        return

    overlap_found, overlap_desc = check_overlap(a_windows)
    print(f"  Windows: {len(a_windows)}  Overlap: {'YES' if overlap_found else 'no'} "
          f"{'(' + overlap_desc + ')' if overlap_found else ''}", flush=True)

    # Raw + unique
    a_raw, a_unique = dedup_trades(a_windows)
    r_raw, r_unique = dedup_trades(r_windows)

    # Per-window
    print(f"\n  {'Window':<22} {'T':>4} {'WR':>5} {'EV':>7} {'PF':>5} {'DD':>5} {'Blk':>4}", flush=True)
    print(f"  {'-'*60}", flush=True)

    for aw, rw in zip(a_windows, r_windows):
        lbl = f"{aw.test_start}->{aw.test_end}"
        blk = (rw.regime_blocked / max(rw.regime_checked, 1)) * 100
        print(f"  A+ {lbl:<19} {aw.test_trades:>4} {aw.test_win_rate*100:>4.1f}% "
              f"{aw.test_expectancy:>+6.2f}R {aw.test_profit_factor:>5.2f} "
              f"{aw.test_max_drawdown:>4.1f}R {'':>4}", flush=True)
        print(f"  RG {lbl:<19} {rw.test_trades:>4} {rw.test_win_rate*100:>4.1f}% "
              f"{rw.test_expectancy:>+6.2f}R {rw.test_profit_factor:>5.2f} "
              f"{rw.test_max_drawdown:>4.1f}R {blk:>3.0f}%", flush=True)

    # Aggregate
    n = len(a_windows)
    a_evs = [w.test_expectancy for w in a_windows]
    r_evs = [w.test_expectancy for w in r_windows]
    a_pfs = [w.test_profit_factor for w in a_windows]
    r_pfs = [w.test_profit_factor for w in r_windows]

    avg_a_ev = sum(a_evs) / n
    avg_r_ev = sum(r_evs) / n
    avg_a_pf = sum(a_pfs) / n
    avg_r_pf = sum(r_pfs) / n
    max_a_dd = max(w.test_max_drawdown for w in a_windows)
    max_r_dd = max(w.test_max_drawdown for w in r_windows)

    a_profs = [w.test_expectancy * w.test_trades for w in a_windows]
    r_profs = [w.test_expectancy * w.test_trades for w in r_windows]
    total_a_profit = sum(a_profs)
    total_r_profit = sum(r_profs)
    a_conc = max(a_profs) / total_a_profit * 100 if total_a_profit > 0 else 0
    r_conc = max(r_profs) / total_r_profit * 100 if total_r_profit > 0 else 0

    a_prof_wins = sum(1 for w in a_windows if w.test_expectancy > 0)
    r_prof_wins = sum(1 for w in r_windows if w.test_expectancy > 0)

    print(f"\n  {'Metric':<35} {'A+ alone':<17} {'+regime gate':<17}", flush=True)
    print(f"  {'':-<35} {'':-<17} {'':-<17}", flush=True)
    print(f"  {'Raw OOS trades':<35} {a_raw:<17} {r_raw:<17}", flush=True)
    print(f"  {'Unique OOS trades':<35} {a_unique:<17} {r_unique:<17}", flush=True)
    print(f"  {'Profitable windows':<35} {a_prof_wins}/{n:<15} {r_prof_wins}/{n:<15}", flush=True)
    print(f"  {'%-profitable windows':<35} {a_prof_wins/n*100:<16.1f}% {r_prof_wins/n*100:<16.1f}%", flush=True)
    print(f"  {'Avg EV':<35} {avg_a_ev:<+17.2f}R {avg_r_ev:<+17.2f}R", flush=True)
    print(f"  {'Avg PF':<35} {avg_a_pf:<17.2f} {avg_r_pf:<17.2f}", flush=True)
    print(f"  {'Max DD':<35} {max_a_dd:<17.1f}R {max_r_dd:<17.1f}R", flush=True)
    print(f"  {'Best window profit share':<35} {a_conc:<16.1f}% {r_conc:<16.1f}%", flush=True)

    # Verdict for regime gate (using unique trades for threshold)
    print(f"\n  {'--- Verdict: A+ + regime gate ---'}", flush=True)
    failures = []
    if r_unique < 100:
        failures.append(f"unique OOS {r_unique} < 100")
    if r_prof_wins / n < 0.7:
        failures.append(f"profitable windows {r_prof_wins}/{n} < 70%")
    if avg_r_ev <= 0:
        failures.append(f"avg EV {avg_r_ev:.2f}R <= 0")
    if avg_r_pf <= 1.2:
        failures.append(f"avg PF {avg_r_pf:.2f} <= 1.2")
    if r_conc > 50:
        failures.append(f"concentration {r_conc:.1f}% > 50%")
    if max_r_dd > 8.0 and r_unique >= 50:
        failures.append(f"max DD {max_r_dd:.1f}R > 8.0R")

    if not failures:
        verdict = "ROBUST_EDGE"
    elif r_unique < 100:
        verdict = "INSUFFICIENT_TRADES"
    else:
        # Check REGIME_SPECIFIC_EDGE or OVERFIT
        half = n // 2
        recent_avg = sum(r_evs[:half]) / half if half > 0 else 0
        old_avg = sum(r_evs[half:]) / (n - half) if (n - half) > 0 else 0
        if recent_avg > 0 and old_avg <= 0 and (n - half) >= 2:
            verdict = "REGIME_SPECIFIC_EDGE"
        else:
            verdict = "OVERFIT_SUSPECTED"

    print(f"  Verdict: {verdict}", flush=True)
    if verdict == "ROBUST_EDGE":
        print(f"  Reason: All criteria met ({n} windows, EV {avg_r_ev:.2f}R, PF {avg_r_pf:.2f}, DD {max_r_dd:.1f}R)", flush=True)
    elif verdict == "INSUFFICIENT_TRADES":
        print(f"  Reason: {failures[0]}", flush=True)
        if failures[1:]:
            print(f"  Additional: {'; '.join(failures[1:])}", flush=True)
    else:
        print(f"  Reason: {'; '.join(failures)}", flush=True)

    print(f"\n  Elapsed: {elapsed:.0f}s", flush=True)
    return verdict, r_unique

# ── Primary Validation (non-overlapping) ──
verdict1, n1 = run_and_report(30, 30, 30, "PRIMARY VALIDATION (non-overlapping)")

# ── Secondary Sensitivity Test (overlapping, deduplicated) ──
verdict2, n2 = run_and_report(30, 30, 15, "SECONDARY SENSITIVITY TEST (overlapping)")

print(f"\n{'='*70}", flush=True)
print("SUMMARY", flush=True)
print(f"{'='*70}", flush=True)
print(f"  Primary (30/30/30):   Verdict={verdict1}  Unique OOS={n1}", flush=True)
print(f"  Secondary (30/30/15): Verdict={verdict2}  Unique OOS={n2}", flush=True)

if n1 >= 100 or n2 >= 100:
    print(f"\n  => Enough OOS trades. Result actionable.", flush=True)
else:
    print(f"\n  => Both modes below 100 unique OOS trades. Verdict: INSUFFICIENT_TRADES.", flush=True)
    print(f"     Cannot conclude ROBUST_EDGE with current data.", flush=True)
