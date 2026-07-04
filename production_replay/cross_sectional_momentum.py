"""
Phase 80B — Cross-Sectional Momentum (CSM) Core — Fixed Data Loader
30-day cross-sectional momentum strategy with diagnostics.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CANDLE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")

# Strategy parameters
LOOKBACK_DAYS = 30
MIN_HISTORY_DAYS = 45  # need at least 45 daily closes
REBALANCE_FREQ = "daily"

# Diagnostics file
DIAG_JSON = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "csm_data_diagnostics.json")
DIAG_TXT = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "csm_data_diagnostics.txt")


def _load_1h_candles(symbol):
    """Load 1-hour candles for a symbol from cache."""
    path = os.path.join(CANDLE_DIR, f"{symbol}_1h.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            candles = json.load(f)
        if not isinstance(candles, list):
            return []
        return candles
    except Exception:
        return []


def _aggregate_to_daily(candles_1h):
    """Aggregate 1-hour candles into daily candles (UTC).
    Returns list of daily candle dicts sorted by date.
    """
    if not candles_1h:
        return []

    daily = {}
    for c in candles_1h:
        ts_raw = c.get("timestamp", 0)
        try:
            ts_ms = int(ts_raw)
        except (ValueError, TypeError):
            continue
        if ts_ms <= 0:
            continue

        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")

        if date_str not in daily:
            daily[date_str] = {
                "date": date_str,
                "open": float(c.get("open", 0) or 0),
                "high": float(c.get("high", 0) or 0),
                "low": float(c.get("low", 0) or 0),
                "close": float(c.get("close", 0) or 0),
                "volume": float(c.get("volume", 0) or 0),
                "candle_count": 1,
            }
        else:
            d = daily[date_str]
            h = float(c.get("high", 0) or 0)
            l = float(c.get("low", 0) or 0)
            if h > d["high"]:
                d["high"] = h
            if l < d["low"]:
                d["low"] = l
            d["close"] = float(c.get("close", 0) or 0)
            d["volume"] = d.get("volume", 0) + float(c.get("volume", 0) or 0)
            d["candle_count"] = d.get("candle_count", 0) + 1

    result = sorted(daily.values(), key=lambda x: x["date"])
    return result


def get_daily_candles(symbol):
    """Get daily candles for a symbol by aggregating 1h data."""
    candles_1h = _load_1h_candles(symbol)
    return _aggregate_to_daily(candles_1h)


def calculate_momentum_30d(daily_candles):
    """Calculate 30-day momentum.
    momentum_30d = close_today / close_30_days_ago - 1
    Returns momentum value or None if insufficient data.
    """
    if len(daily_candles) < LOOKBACK_DAYS + 1:
        return None

    close_today = daily_candles[-1]["close"]
    close_30d_ago = daily_candles[-(LOOKBACK_DAYS + 1)]["close"]

    if close_30d_ago <= 0:
        return None

    momentum = close_today / close_30d_ago - 1
    return momentum


def run_diagnostics():
    """Run full diagnostics on candle cache data.
    Returns diagnostics dict.
    """
    cache_dirs_checked = [CANDLE_DIR]
    files_found = 0
    files_parsed = 0
    rows_loaded = 0
    symbols_with_raw_data = 0
    symbols_with_daily_data = 0
    symbols_eligible = 0
    min_daily_closes = 999999
    max_daily_closes = 0
    all_daily_counts = []
    rejection_reasons = []
    date_range_min = None
    date_range_max = None

    if not os.path.exists(CANDLE_DIR):
        rejection_reasons.append(f"Candle directory not found: {CANDLE_DIR}")
        return _build_diag(cache_dirs_checked, files_found, files_parsed, rows_loaded,
                          symbols_with_raw_data, symbols_with_daily_data, symbols_eligible,
                          all_daily_counts, rejection_reasons, date_range_min, date_range_max)

    files = os.listdir(CANDLE_DIR)
    h1_files = [f for f in files if f.endswith("_1h.json")]
    files_found = len(h1_files)

    for f in h1_files:
        symbol = f.replace("_1h.json", "")
        candles_1h = _load_1h_candles(symbol)
        if not candles_1h:
            continue
        files_parsed += 1
        rows_loaded += len(candles_1h)
        symbols_with_raw_data += 1

        daily = _aggregate_to_daily(candles_1h)
        daily_count = len(daily)
        all_daily_counts.append(daily_count)

        if daily_count > 0:
            symbols_with_daily_data += 1

            # Track date range
            first_date = daily[0]["date"]
            last_date = daily[-1]["date"]
            if date_range_min is None or first_date < date_range_min:
                date_range_min = first_date
            if date_range_max is None or last_date > date_range_max:
                date_range_max = last_date

        if daily_count < min_daily_closes:
            min_daily_closes = daily_count
        if daily_count > max_daily_closes:
            max_daily_closes = daily_count

        if daily_count >= MIN_HISTORY_DAYS:
            symbols_eligible += 1

    if files_found == 0:
        rejection_reasons.append("No 1h candle files found in cache")
    if symbols_with_raw_data == 0:
        rejection_reasons.append("No symbols with raw 1h data")
    if symbols_with_daily_data == 0:
        rejection_reasons.append("No symbols produced daily candles")
    if symbols_eligible == 0:
        if min_daily_closes < 999999:
            rejection_reasons.append(
                f"Insufficient data: max daily closes={max_daily_closes}, "
                f"required={MIN_HISTORY_DAYS}. Need more historical data."
            )
        else:
            rejection_reasons.append("No symbols have enough daily data for 30d momentum")

    if all_daily_counts:
        avg_daily = sum(all_daily_counts) / len(all_daily_counts)
    else:
        avg_daily = 0

    return _build_diag(cache_dirs_checked, files_found, files_parsed, rows_loaded,
                      symbols_with_raw_data, symbols_with_daily_data, symbols_eligible,
                      all_daily_counts, rejection_reasons, date_range_min, date_range_max,
                      min_daily_closes if min_daily_closes < 999999 else 0,
                      max_daily_closes, avg_daily)


def _build_diag(cache_dirs, files_found, files_parsed, rows_loaded,
                raw_sym, daily_sym, eligible, daily_counts, reasons,
                date_min, date_max, min_closes=0, max_closes=0, avg_closes=0):
    """Build diagnostics dict."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cache_dirs_checked": cache_dirs,
        "files_found": files_found,
        "files_parsed": files_parsed,
        "rows_loaded": rows_loaded,
        "symbols_with_raw_data": raw_sym,
        "symbols_with_daily_data": daily_sym,
        "symbols_eligible": eligible,
        "min_daily_closes": min_closes,
        "max_daily_closes": max_closes,
        "avg_daily_closes": round(avg_closes, 1),
        "date_range": f"{date_min} to {date_max}" if date_min and date_max else "N/A",
        "required_history_days": MIN_HISTORY_DAYS,
        "lookback_days": LOOKBACK_DAYS,
        "rejection_reasons": reasons,
        "data_sufficient": eligible > 0,
    }


def write_diagnostics(diag):
    """Write diagnostics to files."""
    os.makedirs(os.path.dirname(DIAG_JSON), exist_ok=True)
    with open(DIAG_JSON, "w", encoding="utf-8") as f:
        json.dump(diag, f, indent=2)

    lines = []
    lines.append("=" * 60)
    lines.append("CSM DATA DIAGNOSTICS")
    lines.append(f"  {diag['timestamp']}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Cache Dirs Checked:     {diag['cache_dirs_checked']}")
    lines.append(f"  Files Found:            {diag['files_found']}")
    lines.append(f"  Files Parsed:           {diag['files_parsed']}")
    lines.append(f"  Rows Loaded:            {diag['rows_loaded']}")
    lines.append(f"  Symbols with Raw Data:  {diag['symbols_with_raw_data']}")
    lines.append(f"  Symbols with Daily:     {diag['symbols_with_daily_data']}")
    lines.append(f"  Symbols Eligible:       {diag['symbols_eligible']}")
    lines.append(f"  Min Daily Closes:       {diag['min_daily_closes']}")
    lines.append(f"  Max Daily Closes:       {diag['max_daily_closes']}")
    lines.append(f"  Avg Daily Closes:       {diag['avg_daily_closes']}")
    lines.append(f"  Date Range:             {diag['date_range']}")
    lines.append(f"  Required History:       {diag['required_history_days']} days")
    lines.append(f"  Lookback:               {diag['lookback_days']} days")
    lines.append(f"  Data Sufficient:        {'YES' if diag['data_sufficient'] else 'NO'}")
    if diag["rejection_reasons"]:
        lines.append("")
        lines.append("  REJECTION REASONS:")
        for r in diag["rejection_reasons"]:
            lines.append(f"    - {r}")
    lines.append("")
    lines.append("=" * 60)

    with open(DIAG_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def get_eligible_symbols(min_days=MIN_HISTORY_DAYS):
    """Get all symbols with sufficient daily data for momentum calculation.
    Returns list of (symbol, daily_candles) tuples.
    """
    if not os.path.exists(CANDLE_DIR):
        return []

    files = os.listdir(CANDLE_DIR)
    h1_files = [f for f in files if f.endswith("_1h.json")]

    eligible = []
    for f in h1_files:
        symbol = f.replace("_1h.json", "")
        daily = get_daily_candles(symbol)
        if len(daily) >= min_days:
            eligible.append((symbol, daily))

    return eligible


def rank_by_momentum(eligible_symbols):
    """Rank all eligible symbols by 30-day momentum.
    Returns sorted list of (symbol, momentum, daily_candles) tuples.
    """
    ranked = []
    for symbol, daily in eligible_symbols:
        mom = calculate_momentum_30d(daily)
        if mom is not None:
            ranked.append((symbol, mom, daily))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def generate_baskets(ranked_symbols, top_n, bottom_n):
    """Generate long and short baskets.
    Long top_n strongest, short bottom_n weakest.
    Returns dict with long_basket, short_basket, metadata.
    """
    if len(ranked_symbols) < top_n + bottom_n:
        return {
            "long_basket": [],
            "short_basket": [],
            "error": f"Insufficient symbols: {len(ranked_symbols)} < {top_n + bottom_n}",
        }

    long_basket = []
    for symbol, mom, daily in ranked_symbols[:top_n]:
        long_basket.append({
            "symbol": symbol,
            "momentum_30d": round(mom, 6),
            "side": "LONG",
            "close": daily[-1]["close"],
        })

    short_basket = []
    for symbol, mom, daily in ranked_symbols[-bottom_n:]:
        short_basket.append({
            "symbol": symbol,
            "momentum_30d": round(mom, 6),
            "side": "SHORT",
            "close": daily[-1]["close"],
        })

    return {
        "long_basket": long_basket,
        "short_basket": short_basket,
        "total_symbols_ranked": len(ranked_symbols),
        "long_avg_momentum": round(sum(s["momentum_30d"] for s in long_basket) / top_n, 6) if top_n > 0 else 0,
        "short_avg_momentum": round(sum(s["momentum_30d"] for s in short_basket) / bottom_n, 6) if bottom_n > 0 else 0,
    }


def get_current_signal(top_n=3, bottom_n=3):
    """Get current CSM signal with long/short baskets.
    Returns dict with baskets, timestamp, and metadata.
    """
    eligible = get_eligible_symbols()
    ranked = rank_by_momentum(eligible)
    baskets = generate_baskets(ranked, top_n, bottom_n)

    has_signal = len(ranked) >= top_n + bottom_n

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "top_n": top_n,
        "bottom_n": bottom_n,
        "eligible_symbols": len(eligible),
        "ranked_symbols": len(ranked),
        "has_valid_signal": has_signal,
        "signal_status": "VALID" if has_signal else "SIGNAL_UNAVAILABLE_DATA_MISSING",
        "long_basket": baskets.get("long_basket", []),
        "short_basket": baskets.get("short_basket", []),
        "long_avg_momentum": baskets.get("long_avg_momentum", 0),
        "short_avg_momentum": baskets.get("short_avg_momentum", 0),
        "error": baskets.get("error"),
        "live_trading": "NO",
        "real_orders": "NO",
    }


def _get_all_dates(min_days=1):
    """Get all unique dates across all symbols."""
    eligible = get_eligible_symbols(min_days=min_days)
    all_dates = set()
    for symbol, daily in eligible:
        for d in daily:
            all_dates.add(d["date"])
    return sorted(all_dates)


if __name__ == "__main__":
    print("=" * 60)
    print("CROSS-SECTIONAL MOMENTUM — DATA DIAGNOSTICS")
    print("=" * 60)

    diag = run_diagnostics()
    write_diagnostics(diag)

    print(f"\nFiles found:        {diag['files_found']}")
    print(f"Symbols with data:  {diag['symbols_with_raw_data']}")
    print(f"Symbols with daily: {diag['symbols_with_daily_data']}")
    print(f"Symbols eligible:   {diag['symbols_eligible']}")
    print(f"Max daily closes:   {diag['max_daily_closes']}")
    print(f"Date range:         {diag['date_range']}")
    print(f"Data sufficient:    {'YES' if diag['data_sufficient'] else 'NO'}")
    if diag["rejection_reasons"]:
        print("\nRejection reasons:")
        for r in diag["rejection_reasons"]:
            print(f"  - {r}")

    if diag["data_sufficient"]:
        eligible = get_eligible_symbols()
        ranked = rank_by_momentum(eligible)
        print(f"\nEligible: {len(eligible)}  Ranked: {len(ranked)}")
        for n in [3, 5, 10, 15]:
            baskets = generate_baskets(ranked, n, n)
            print(f"\n--- Top {n} / Bottom {n} ---")
            print("LONG:")
            for s in baskets.get("long_basket", []):
                print(f"  {s['symbol']:15s} mom={s['momentum_30d']:+.4f}")
            print("SHORT:")
            for s in baskets.get("short_basket", []):
                print(f"  {s['symbol']:15s} mom={s['momentum_30d']:+.4f}")

    print(f"\nLive Trading: NO")
    print(f"Real Orders:  NO")
