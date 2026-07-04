"""
Phase 80 — Cross-Sectional Momentum (CSM) Core
30-day cross-sectional momentum strategy.
Calculates momentum, ranks symbols, generates long/short baskets.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CANDLE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")

# Strategy parameters
LOOKBACK_DAYS = 30
MIN_HISTORY_DAYS = 40  # need at least 40 days of data
REBALANCE_FREQ = "daily"

# Universe filters
MIN_VOLUME_USD = 50000.0  # 24h min volume


def _load_1h_candles(symbol):
    """Load 1-hour candles for a symbol from cache."""
    path = os.path.join(CANDLE_DIR, f"{symbol}_1h.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            candles = json.load(f)
        return candles
    except Exception:
        return []


def _aggregate_to_daily(candles_1h):
    """Aggregate 1-hour candles into daily candles.
    Each daily candle: date (YYYY-MM-DD), open, high, low, close, volume.
    Uses UTC date grouping.
    Returns list of daily candle dicts sorted by date.
    """
    if not candles_1h:
        return []

    daily = {}
    for c in candles_1h:
        ts_ms = int(c.get("timestamp", 0))
        if ts_ms <= 0:
            continue
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")

        if date_str not in daily:
            daily[date_str] = {
                "date": date_str,
                "open": c.get("open", 0),
                "high": c.get("high", 0),
                "low": c.get("low", 0),
                "close": c.get("close", 0),
                "volume": c.get("volume", 0),
            }
        else:
            d = daily[date_str]
            d["high"] = max(d["high"], c.get("high", 0))
            d["low"] = min(d["low"], c.get("low", 0))
            d["close"] = c.get("close", 0)  # last candle close = daily close
            d["volume"] = d.get("volume", 0) + c.get("volume", 0)

    result = sorted(daily.values(), key=lambda x: x["date"])
    return result


def get_daily_candles(symbol):
    """Get daily candles for a symbol by aggregating 1h data."""
    candles_1h = _load_1h_candles(symbol)
    return _aggregate_to_daily(candles_1h)


def calculate_momentum_30d(daily_candles):
    """Calculate 30-day momentum for a symbol.
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

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "top_n": top_n,
        "bottom_n": bottom_n,
        "eligible_symbols": len(eligible),
        "ranked_symbols": len(ranked),
        "long_basket": baskets.get("long_basket", []),
        "short_basket": baskets.get("short_basket", []),
        "long_avg_momentum": baskets.get("long_avg_momentum", 0),
        "short_avg_momentum": baskets.get("short_avg_momentum", 0),
        "live_trading": "NO",
        "real_orders": "NO",
    }


def _get_all_dates():
    """Get all unique dates across all symbols."""
    eligible = get_eligible_symbols(min_days=1)
    all_dates = set()
    for symbol, daily in eligible:
        for d in daily:
            all_dates.add(d["date"])
    return sorted(all_dates)


if __name__ == "__main__":
    print("=" * 60)
    print("CROSS-SECTIONAL MOMENTUM — SIGNAL")
    print("=" * 60)

    eligible = get_eligible_symbols()
    ranked = rank_by_momentum(eligible)

    print(f"\nEligible symbols: {len(eligible)}")
    print(f"Ranked symbols:   {len(ranked)}")

    for n in [3, 5, 10, 15]:
        baskets = generate_baskets(ranked, n, n)
        print(f"\n--- Top {n} / Bottom {n} ---")
        print("LONG:")
        for s in baskets.get("long_basket", []):
            print(f"  {s['symbol']:15s} mom={s['momentum_30d']:+.4f}  close={s['close']:.6f}")
        print("SHORT:")
        for s in baskets.get("short_basket", []):
            print(f"  {s['symbol']:15s} mom={s['momentum_30d']:+.4f}  close={s['close']:.6f}")

    print(f"\nLive Trading: NO")
    print(f"Real Orders:  NO")
