"""
Phase 80 — CSM Backtest Engine
Walk-forward backtesting for cross-sectional momentum strategy.
Tests 4 variants (top 3/5/10/15), in-sample/out-of-sample split,
1-day delay variant, fees and slippage.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cross_sectional_momentum import (
    get_daily_candles, get_eligible_symbols, _get_all_dates,
    LOOKBACK_DAYS
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
REPORT_JSON = os.path.join(RESULTS_DIR, "csm_backtest_report.json")
REPORT_TXT = os.path.join(RESULTS_DIR, "csm_backtest_report.txt")

# Backtest parameters
CAPITAL = 400.0
FEE_RATE = 0.0004  # 0.04% per side
SLIPPAGE_RATE = 0.0005  # 0.05% per side
REBALANCE_COST = 2 * (FEE_RATE + SLIPPAGE_RATE)  # round-trip cost
MIN_HISTORY = LOOKBACK_DAYS + 10  # need 40+ days

# Portfolio variants
VARIANTS = [
    {"label": "top3_bottom3", "top_n": 3, "bottom_n": 3},
    {"label": "top5_bottom5", "top_n": 5, "bottom_n": 5},
    {"label": "top10_bottom10", "top_n": 10, "bottom_n": 10},
    {"label": "top15_bottom15", "top_n": 15, "bottom_n": 15},
]


def _load_all_daily_candles():
    """Load daily candles for all eligible symbols.
    Returns dict: symbol -> list of daily candle dicts.
    """
    eligible = get_eligible_symbols(min_days=MIN_HISTORY)
    result = {}
    for symbol, daily in eligible:
        result[symbol] = daily
    return result


def _get_trading_dates(all_daily):
    """Get sorted list of all unique trading dates."""
    dates = set()
    for symbol, daily in all_daily.items():
        for d in daily:
            dates.add(d["date"])
    return sorted(dates)


def _get_close_on_date(daily, date_str):
    """Get closing price for a symbol on a given date."""
    for d in daily:
        if d["date"] == date_str:
            return d["close"]
    return None


def _calculate_momentum(all_daily, date_str, lookback=LOOKBACK_DAYS):
    """Calculate 30-day momentum for all symbols on a given date.
    Returns list of (symbol, momentum) sorted descending.
    """
    momentum = []
    for symbol, daily in all_daily.items():
        # Find index of date_str
        idx = None
        for i, d in enumerate(daily):
            if d["date"] == date_str:
                idx = i
                break
        if idx is None or idx < lookback:
            continue

        close_today = daily[idx]["close"]
        close_30d = daily[idx - lookback]["close"]
        if close_30d <= 0:
            continue

        mom = close_today / close_30d - 1
        momentum.append((symbol, mom))

    momentum.sort(key=lambda x: x[1], reverse=True)
    return momentum


def _calculate_daily_returns(all_daily, date_from, date_to):
    """Calculate daily return for each symbol between two dates."""
    returns = {}
    for symbol, daily in all_daily.items():
        close_from = _get_close_on_date(daily, date_from)
        close_to = _get_close_on_date(daily, date_to)
        if close_from is not None and close_to is not None and close_from > 0:
            returns[symbol] = close_to / close_from - 1
    return returns


def _run_backtest(all_daily, trading_dates, top_n, bottom_n, delay=False):
    """Run backtest for a single variant.
    Returns dict with equity curve, stats, and metadata.
    """
    equity = CAPITAL
    equity_curve = [{"date": trading_dates[0], "equity": equity}]
    positions = {}  # symbol -> {"side": "LONG"/"SHORT", "weight": float}
    turnover_total = 0
    rebalance_count = 0
    holdings_days = 0

    # Skip first MIN_HISTORY days
    start_idx = MIN_HISTORY

    for i in range(start_idx, len(trading_dates)):
        date = trading_dates[i]
        prev_date = trading_dates[i - 1] if i > 0 else None

        # Calculate daily return for existing positions
        if prev_date:
            daily_returns = _calculate_daily_returns(all_daily, prev_date, date)
            portfolio_return = 0
            for sym, pos in positions.items():
                ret = daily_returns.get(sym, 0)
                if pos["side"] == "LONG":
                    portfolio_return += pos["weight"] * ret
                else:
                    portfolio_return += pos["weight"] * (-ret)

            equity *= (1 + portfolio_return)
            holdings_days += 1

        # Rebalance on each day
        # Use momentum from lookback period (or 1 day delayed if delay=True)
        mom_date_idx = i - 1 if delay else i
        if mom_date_idx < start_idx:
            equity_curve.append({"date": date, "equity": equity})
            continue

        mom_date = trading_dates[mom_date_idx]
        momentum = _calculate_momentum(all_daily, mom_date, LOOKBACK_DAYS)

        if len(momentum) < top_n + bottom_n:
            equity_curve.append({"date": date, "equity": equity})
            continue

        # Form new baskets
        new_positions = {}
        for symbol, mom in momentum[:top_n]:
            new_positions[symbol] = {"side": "LONG", "weight": 1.0 / (top_n + bottom_n)}
        for symbol, mom in momentum[-bottom_n:]:
            new_positions[symbol] = {"side": "SHORT", "weight": 1.0 / (top_n + bottom_n)}

        # Calculate turnover
        old_syms = set(positions.keys())
        new_syms = set(new_positions.keys())
        changed = old_syms != new_syms
        if changed:
            # Estimate turnover as fraction of portfolio changed
            exited = old_syms - new_syms
            entered = new_syms - old_syms
            turnover = (len(exited) + len(entered)) / max(1, top_n + bottom_n)
            turnover_total += turnover

            # Apply rebalance cost
            equity *= (1 - REBALANCE_COST * turnover * 0.5)
            rebalance_count += 1

        positions = new_positions
        equity_curve.append({"date": date, "equity": equity})

    return {
        "equity_curve": equity_curve,
        "final_equity": equity,
        "total_return": (equity / CAPITAL - 1),
        "turnover_total": turnover_total,
        "rebalance_count": rebalance_count,
        "holdings_days": holdings_days,
    }


def _calculate_stats(equity_curve, trading_days_per_year=365):
    """Calculate performance statistics from equity curve."""
    if len(equity_curve) < 2:
        return {}

    equities = [e["equity"] for e in equity_curve]
    dates = [e["date"] for e in equity_curve]

    # Daily returns
    daily_returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            daily_returns.append(equities[i] / equities[i - 1] - 1)

    if not daily_returns:
        return {}

    # CAGR
    years = len(daily_returns) / trading_days_per_year
    total_return = equities[-1] / equities[0] - 1
    cagr = (1 + total_return) ** (1 / max(years, 0.01)) - 1 if total_return > -1 else -1

    # Sharpe ratio (annualized, assuming 0% risk-free rate)
    avg_ret = sum(daily_returns) / len(daily_returns)
    var_ret = sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns)
    std_ret = math.sqrt(var_ret) if var_ret > 0 else 0.0001
    sharpe = (avg_ret / std_ret) * math.sqrt(trading_days_per_year)

    # Max drawdown
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Monthly returns
    monthly = {}
    for i, e in enumerate(equity_curve):
        month = e["date"][:7]  # YYYY-MM
        if month not in monthly:
            monthly[month] = {"first": e["equity"], "last": e["equity"]}
        monthly[month]["last"] = e["equity"]

    monthly_returns = []
    prev_last = None
    for month in sorted(monthly.keys()):
        m = monthly[month]
        if prev_last is not None and prev_last > 0:
            monthly_returns.append(m["last"] / prev_last - 1)
        prev_last = m["last"]

    months_green = sum(1 for r in monthly_returns if r > 0)
    total_months = len(monthly_returns)
    monthly_win_rate = months_green / total_months if total_months > 0 else 0

    # Worst month
    worst_month = min(monthly_returns) if monthly_returns else 0

    # Average holding period
    avg_holding = len(daily_returns) / max(1, total_months) if total_months > 0 else 0

    return {
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "monthly_win_rate": round(monthly_win_rate, 4),
        "months_green": months_green,
        "total_months": total_months,
        "worst_month": round(worst_month, 4),
        "avg_holding_days": round(avg_holding, 1),
        "daily_volatility": round(std_ret, 6),
        "start_date": dates[0],
        "end_date": dates[-1],
    }


def _split_is_oos(equity_curve):
    """Split equity curve into in-sample (first 50%) and out-of-sample (second 50%)."""
    mid = len(equity_curve) // 2
    is_curve = equity_curve[:mid]
    oos_curve = equity_curve[mid:]
    return is_curve, oos_curve


def _yearly_split(equity_curve):
    """Split equity curve by year."""
    yearly = {}
    for e in equity_curve:
        year = e["date"][:4]
        if year not in yearly:
            yearly[year] = []
        yearly[year].append(e)
    return yearly


def run_full_backtest():
    """Run full backtest across all variants.
    Returns report dict.
    """
    print("Loading daily candles...")
    all_daily = _load_all_daily_candles()
    trading_dates = _get_trading_dates(all_daily)

    print(f"Symbols with data: {len(all_daily)}")
    print(f"Trading dates: {len(trading_dates)} ({trading_dates[0]} to {trading_dates[-1]})")

    variants_results = []

    for v in VARIANTS:
        label = v["label"]
        top_n = v["top_n"]
        bottom_n = v["bottom_n"]

        print(f"\n--- Running {label} ---")

        # Normal backtest
        result = _run_backtest(all_daily, trading_dates, top_n, bottom_n, delay=False)
        stats = _calculate_stats(result["equity_curve"])

        # 1-day delay variant
        result_delay = _run_backtest(all_daily, trading_dates, top_n, bottom_n, delay=True)
        stats_delay = _calculate_stats(result_delay["equity_curve"])

        # IS/OOS split
        is_curve, oos_curve = _split_is_oos(result["equity_curve"])
        is_stats = _calculate_stats(is_curve)
        oos_stats = _calculate_stats(oos_curve)

        # Yearly split
        yearly = _yearly_split(result["equity_curve"])
        yearly_stats = {}
        for year, curve in sorted(yearly.items()):
            yearly_stats[year] = _calculate_stats(curve)

        # Rejection check
        oos_sharpe = oos_stats.get("sharpe", 0)
        max_dd = stats.get("max_drawdown", 1)
        rejected = oos_sharpe <= 0.5 or max_dd > 0.5

        variant_result = {
            "label": label,
            "top_n": top_n,
            "bottom_n": bottom_n,
            "rejected": rejected,
            "rejection_reason": [],
            "overall": stats,
            "delay_1d": stats_delay,
            "in_sample": is_stats,
            "out_of_sample": oos_stats,
            "yearly": yearly_stats,
            "final_equity": result["final_equity"],
            "rebalance_count": result["rebalance_count"],
            "turnover_total": round(result["turnover_total"], 2),
        }

        if oos_sharpe <= 0.5:
            variant_result["rejection_reason"].append(f"OOS Sharpe {oos_sharpe:.2f} <= 0.5")
        if max_dd > 0.5:
            variant_result["rejection_reason"].append(f"Max DD {max_dd:.1%} > 50%")

        variants_results.append(variant_result)

        print(f"  Overall Sharpe: {stats.get('sharpe', 0):.2f}")
        print(f"  OOS Sharpe:     {oos_sharpe:.2f}")
        print(f"  Max DD:         {max_dd:.1%}")
        print(f"  CAGR:           {stats.get('cagr', 0):.1%}")
        print(f"  Rejected:       {rejected}")

    # Find best variant
    valid_variants = [v for v in variants_results if not v["rejected"]]
    if valid_variants:
        best = max(valid_variants, key=lambda x: x["overall"].get("sharpe", 0))
    else:
        best = max(variants_results, key=lambda x: x["overall"].get("sharpe", 0))

    # Generate current signal with best variant
    from cross_sectional_momentum import rank_by_momentum, generate_baskets, get_eligible_symbols
    eligible = get_eligible_symbols()
    ranked = rank_by_momentum(eligible)
    current_baskets = generate_baskets(ranked, best["top_n"], best["bottom_n"])

    report = {
        "mode": "csm_backtest",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "live_trading": False,
        "real_orders": False,
        "capital": CAPITAL,
        "fee_rate": FEE_RATE,
        "slippage_rate": SLIPPAGE_RATE,
        "lookback_days": LOOKBACK_DAYS,
        "symbols_used": len(all_daily),
        "trading_dates": len(trading_dates),
        "date_range": f"{trading_dates[0]} to {trading_dates[-1]}",
        "best_variant": best["label"],
        "best_top_n": best["top_n"],
        "best_bottom_n": best["bottom_n"],
        "overall_sharpe": best["overall"].get("sharpe", 0),
        "overall_cagr": best["overall"].get("cagr", 0),
        "overall_max_drawdown": best["overall"].get("max_drawdown", 0),
        "overall_monthly_win_rate": best["overall"].get("monthly_win_rate", 0),
        "oos_sharpe": best["out_of_sample"].get("sharpe", 0),
        "is_sharpe": best["in_sample"].get("sharpe", 0),
        "delay_1d_sharpe": best["delay_1d"].get("sharpe", 0),
        "months_green": best["overall"].get("months_green", 0),
        "total_months": best["overall"].get("total_months", 0),
        "worst_month": best["overall"].get("worst_month", 0),
        "current_long_basket": current_baskets.get("long_basket", []),
        "current_short_basket": current_baskets.get("short_basket", []),
        "verdict": "LIVE_REVIEW_READY" if (valid_variants and best["oos_sharpe"] > 0.5) else "PAPER_ONLY",
        "status": "PAPER_ONLY",
        "variants": variants_results,
        "warnings": [],
    }

    # Write reports
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    _write_txt_report(report)
    return report


def _write_txt_report(report):
    """Write human-readable TXT report."""
    lines = []
    lines.append("=" * 60)
    lines.append("CSM BACKTEST REPORT")
    lines.append(f"  {report['timestamp']}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Best Variant:      {report['best_variant']}")
    lines.append(f"  Status:            {report['status']}")
    lines.append(f"  Live Trading:      NO")
    lines.append(f"  Real Orders:       NO")
    lines.append(f"  Capital:           {report['capital']} USDT")
    lines.append(f"  Fee:               {report['fee_rate']:.2%} per side")
    lines.append(f"  Slippage:          {report['slippage_rate']:.2%} per side")
    lines.append(f"  Symbols Used:      {report['symbols_used']}")
    lines.append(f"  Trading Dates:     {report['trading_dates']}")
    lines.append(f"  Date Range:        {report['date_range']}")
    lines.append("")

    lines.append("  OVERALL PERFORMANCE (Best Variant):")
    lines.append(f"    Sharpe:            {report['overall_sharpe']:.4f}")
    lines.append(f"    CAGR:              {report['overall_cagr']:.2%}")
    lines.append(f"    Max Drawdown:      {report['overall_max_drawdown']:.2%}")
    lines.append(f"    Monthly Win Rate:  {report['overall_monthly_win_rate']:.1%}")
    lines.append(f"    Months Green:      {report['months_green']}/{report['total_months']}")
    lines.append(f"    Worst Month:       {report['worst_month']:.2%}")
    lines.append("")
    lines.append("  SPLIT PERFORMANCE:")
    lines.append(f"    In-Sample Sharpe:  {report['is_sharpe']:.4f}")
    lines.append(f"    OOS Sharpe:        {report['oos_sharpe']:.4f}")
    lines.append(f"    1-Day Delay Sharpe:{report['delay_1d_sharpe']:.4f}")
    lines.append("")

    lines.append("  ALL VARIANTS:")
    for v in report.get("variants", []):
        marker = " [REJECTED]" if v["rejected"] else ""
        lines.append(f"    {v['label']:15s} Sharpe={v['overall'].get('sharpe', 0):.2f} "
                     f"CAGR={v['overall'].get('cagr', 0):.1%} "
                     f"MaxDD={v['overall'].get('max_drawdown', 0):.1%}{marker}")
        if v["rejection_reason"]:
            for r in v["rejection_reason"]:
                lines.append(f"      Reason: {r}")
    lines.append("")

    lines.append("  CURRENT BASKETS:")
    lines.append("    LONG:")
    for s in report.get("current_long_basket", []):
        lines.append(f"      {s['symbol']:15s} mom={s['momentum_30d']:+.4f}")
    lines.append("    SHORT:")
    for s in report.get("current_short_basket", []):
        lines.append(f"      {s['symbol']:15s} mom={s['momentum_30d']:+.4f}")
    lines.append("")

    lines.append("  SAFETY:")
    lines.append(f"    Live Trading: NO")
    lines.append(f"    Real Orders:  NO")
    lines.append(f"    Execution:    read_only")
    lines.append("")
    lines.append("  WARNING: No real orders placed. Paper/backtest only.")
    lines.append("=" * 60)

    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    report = run_full_backtest()
    print(f"\nBest variant: {report['best_variant']}")
    print(f"Sharpe: {report['overall_sharpe']:.2f}")
    print(f"CAGR: {report['overall_cagr']:.1%}")
    print(f"Max DD: {report['overall_max_drawdown']:.1%}")
    print(f"Verdict: {report['verdict']}")
