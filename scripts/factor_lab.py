"""Cross-sectional factor lab: daily-rebalanced long/short portfolios.

Tests slow, portfolio-style factors on the BingX perp universe — a different
strategy space from the intraday candle patterns in production_replay:

  - momentum (7d / 30d): long past winners, short past losers
  - short-term reversal (2d / 5d): the opposite
  - funding crowding (1d / 3d): long negative-funding, short positive-funding

Honest accounting (same discipline as the fixed breadwinner engines):
  - signals use only data strictly before the rebalance day
  - returns are next-day close-to-close, after the signal is known
  - taker fees (0.05%/side) charged on actual portfolio turnover
  - funding PnL accrued from real 8h funding history where available
    (longs pay positive funding, shorts receive it)
  - 70/30 time split: OOS is strictly the later period
  - robustness battery: top-50 liquidity universe, 1-day execution lag,
    long/short leg decomposition, quarterly breakdown

KNOWN BIASES (cannot be fixed with this data — read before trusting output):
  - Survivorship: the universe is today's listings; delisted coins are
    absent, which inflates momentum-style results by an unknown amount.
  - No slippage model: small-cap legs will cost more than taker fee.

Requires: python scripts/download_factor_data.py  (run first)

Research only — never places orders, never enables live trading.

Usage:
    python scripts/factor_lab.py
"""

import json, math, os
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DAILY_DIR = os.path.join(REPO, "runtime_state", "factor_data", "daily")
FUNDING_DIR = os.path.join(REPO, "runtime_state", "factor_data", "funding")
OUT_PATH = os.path.join(REPO, "deploy_results", "factor_lab_report.json")

DAY_MS = 86400000
TAKER_FEE = 0.0005


def load():
    daily, dollar_vol, fund = {}, {}, {}
    for f in os.listdir(DAILY_DIR):
        sym = f.replace(".json", "")
        rows = json.load(open(os.path.join(DAILY_DIR, f)))
        daily[sym] = {r["t"]: r["close"] for r in rows}
        dollar_vol[sym] = mean(r["close"] * r["volume"] for r in rows)
    if os.path.isdir(FUNDING_DIR):
        for f in os.listdir(FUNDING_DIR):
            sym = f.replace(".json", "")
            rows = json.load(open(os.path.join(FUNDING_DIR, f)))
            by_day = defaultdict(float)
            for r in rows:
                by_day[(r["t"] // DAY_MS) * DAY_MS] += r["rate"]
            fund[sym] = dict(by_day)
    return daily, fund, dollar_vol


def momentum_signal(daily, sym, day, lookback):
    c = daily[sym]
    p0, p1 = c.get(day - lookback * DAY_MS), c.get(day - DAY_MS)
    if not p0 or not p1 or p0 <= 0:
        return None
    return p1 / p0 - 1


def funding_signal(fund, sym, day, lookback):
    vals = [fund.get(sym, {}).get(day - k * DAY_MS) for k in range(1, lookback + 1)]
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None


def run(daily, fund, symbols, signal_fn, long_low, n_side, lag_days=0, legs="both"):
    all_days = sorted({d for s in symbols for d in daily[s]})
    days = all_days[35:-1 - lag_days]
    port, prev_w = [], {}
    for day in days:
        entry_day = day + lag_days * DAY_MS
        nxt = entry_day + DAY_MS
        scored = []
        for sym in symbols:
            c = daily[sym]
            if entry_day not in c or nxt not in c:
                continue
            sc = signal_fn(sym, day)
            if sc is None:
                continue
            scored.append((sc, sym))
        if len(scored) < 40:
            continue
        scored.sort()
        lo = [s for _, s in scored[:n_side]]
        hi = [s for _, s in scored[-n_side:]]
        longs, shorts = (lo, hi) if long_low else (hi, lo)
        w = {}
        if legs in ("both", "long"):
            for s in longs:
                w[s] = 1.0 / n_side / (2 if legs == "both" else 1)
        if legs in ("both", "short"):
            for s in shorts:
                w[s] = -1.0 / n_side / (2 if legs == "both" else 1)
        turnover = sum(abs(w.get(s, 0) - prev_w.get(s, 0))
                       for s in set(w) | set(prev_w)) / 2
        pnl = -turnover * 2 * TAKER_FEE
        for s, wt in w.items():
            r = daily[s][nxt] / daily[s][entry_day] - 1
            f = fund.get(s, {}).get(nxt, 0.0)
            pnl += wt * r - wt * f
        port.append((day, pnl))
        prev_w = w
    return port


def stats(rs):
    if len(rs) < 30:
        return {"days": len(rs), "insufficient": True}
    mu, sd = mean(rs), pstdev(rs) or 1e-12
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in rs:
        eq *= (1 + r)
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return {"days": len(rs), "ann_ret_pct": round(((1 + mu) ** 365 - 1) * 100, 1),
            "sharpe": round(mu / sd * math.sqrt(365), 2),
            "max_dd_pct": round(dd * 100, 1), "total_pct": round((eq - 1) * 100, 1)}


def report(label, port):
    rs = [r for _, r in port]
    split = int(len(rs) * 0.7)
    out = {"label": label, "all": stats(rs), "in_sample": stats(rs[:split]),
           "out_of_sample": stats(rs[split:])}
    q, m = defaultdict(list), defaultdict(list)
    for d, r in port:
        dt = datetime.fromtimestamp(d / 1000, tz=timezone.utc)
        q[f"{dt.year}Q{(dt.month - 1) // 3 + 1}"].append(r)
        m[f"{dt.year}-{dt.month:02d}"].append(r)
    out["quarterly_pct"] = {k: round((math.prod(1 + x for x in v) - 1) * 100, 1)
                            for k, v in sorted(q.items())}
    monthly = [math.prod(1 + x for x in v) - 1 for v in m.values()]
    out["positive_months"] = f"{sum(1 for x in monthly if x > 0)}/{len(monthly)}"
    return out


def main():
    daily, fund, dollar_vol = load()
    all_syms = sorted(daily)
    top50 = sorted(dollar_vol, key=lambda s: -dollar_vol[s])[:50]
    print(f"universe: {len(all_syms)} symbols, funding for {len(fund)}")

    mom = lambda lb: (lambda s, d: momentum_signal(daily, s, d, lb))
    fnd = lambda lb: (lambda s, d: funding_signal(fund, s, d, lb))

    runs = [
        ("momentum_30d", all_syms, mom(30), False, 15, 0, "both"),
        ("momentum_30d top50", top50, mom(30), False, 8, 0, "both"),
        ("momentum_30d 1d-lag", all_syms, mom(30), False, 15, 1, "both"),
        ("momentum_30d long-leg", all_syms, mom(30), False, 15, 0, "long"),
        ("momentum_30d short-leg", all_syms, mom(30), False, 15, 0, "short"),
        ("momentum_7d", all_syms, mom(7), False, 15, 0, "both"),
        ("reversal_2d", all_syms, mom(2), True, 15, 0, "both"),
        ("reversal_5d", all_syms, mom(5), True, 15, 0, "both"),
        ("funding_crowding_1d", all_syms, fnd(1), True, 15, 0, "both"),
        ("funding_crowding_3d", all_syms, fnd(3), True, 15, 0, "both"),
    ]
    results = []
    for label, syms, fn, long_low, n, lag, legs in runs:
        results.append(report(label, run(daily, fund, syms, fn, long_low, n, lag, legs)))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    payload = {
        "mode": "factor_lab",
        "research_only": True,
        "live_trading_enabled": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fee_model": "taker 0.05%/side on turnover, real funding where available",
        "known_biases": ["survivorship (universe = today's listings)",
                          "no slippage model"],
        "results": results,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, indent=1)
    for r in results:
        a, i, o = r["all"], r["in_sample"], r["out_of_sample"]
        print(f"\n{r['label']}")
        print(f"  ALL {a.get('days')}d: ann={a.get('ann_ret_pct')}% sharpe={a.get('sharpe')} maxDD={a.get('max_dd_pct')}%")
        print(f"  IS sharpe={i.get('sharpe')} | OOS sharpe={o.get('sharpe')} | +months {r['positive_months']}")
    print(f"\n[JSON] {OUT_PATH}")


if __name__ == "__main__":
    main()
