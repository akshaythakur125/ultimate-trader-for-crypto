"""Historical market data fetcher.

Downloads OHLCV, funding rate, and open interest data from BingX (primary)
or Binance (fallback) via CCXT. Caches results locally to avoid re-downloading.

Offline research only — never enables live trading.
"""

import json, os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ccxt

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")

SUPPORTED_TIMEFRAMES = ["15m", "30m", "1h", "4h"]
DEFAULT_LOOKBACK_DAYS = 90
MAX_CANDLES_PER_REQUEST = 1000


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}_{timeframe}.json")


def _read_cache(symbol: str, timeframe: str) -> list | None:
    path = _cache_path(symbol, timeframe)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(symbol: str, timeframe: str, data: list):
    path = _cache_path(symbol, timeframe)
    with open(path, "w") as f:
        json.dump(data, f)


def create_exchange(prefer_bingx: bool = True):
    """Create a CCXT exchange instance. Primary: BingX. Fallback: Binance."""
    if prefer_bingx:
        try:
            ex = ccxt.bingx()
            ex.load_markets()
            return ex, "bingx"
        except Exception:
            pass
    try:
        ex = ccxt.binance()
        ex.load_markets()
        return ex, "binance"
    except Exception:
        return None, None


def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    use_cache: bool = True,
) -> list:
    """Fetch OHLCV candles for a symbol/timeframe. Returns list of [ts, o, h, l, c, v]."""
    if use_cache:
        cached = _read_cache(symbol, timeframe)
        if cached and len(cached) > 100:
            return cached

    _ensure_cache_dir()
    exchange, exchange_name = create_exchange()
    if exchange is None:
        return []

    since = exchange.parse8601(
        (datetime.now(timezone.utc).timestamp() - lookback_days * 86400) * 1000
    )
    all_candles = []
    try:
        while True:
            candles = exchange.fetch_ohclv(symbol, timeframe, since=since, limit=MAX_CANDLES_PER_REQUEST)
            if not candles:
                break
            all_candles.extend(candles)
            if len(candles) < MAX_CANDLES_PER_REQUEST:
                break
            since = candles[-1][0] + 1
            time.sleep(0.5)
    except Exception:
        pass

    # Deduplicate by timestamp
    seen = set()
    deduped = []
    for c in all_candles:
        ts = c[0]
        if ts not in seen:
            seen.add(ts)
            deduped.append(c)
    deduped.sort(key=lambda x: x[0])

    if use_cache and len(deduped) > 100:
        _write_cache(symbol, timeframe, deduped)

    return deduped


def fetch_multiple_symbols(
    symbols: list[str],
    timeframe: str = "1h",
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, list]:
    """Fetch OHLCV for multiple symbols. Returns dict of symbol -> candles."""
    result = {}
    for sym in symbols:
        candles = fetch_ohclv(sym, timeframe, lookback_days)
        if candles:
            result[sym] = candles
    return result


def fetch_funding_rate_history(symbol: str, lookback_days: int = 90) -> list:
    """Fetch funding rate history for a symbol."""
    exchange, _ = create_exchange()
    if exchange is None:
        return []
    try:
        since = exchange.parse8601(
            (datetime.now(timezone.utc).timestamp() - lookback_days * 86400) * 1000
        )
        rates = exchange.fetch_funding_rate_history(symbol, since=since)
        return rates
    except Exception:
        return []


def get_top_usdt_perps(limit: int = 20) -> list[str]:
    """Get a list of top USDT perpetual symbols from BingX."""
    exchange, _ = create_exchange()
    if exchange is None:
        return []
    try:
        markets = exchange.load_markets()
        usdt_perps = [
            s for s, m in markets.items()
            if m.get("linear") and m.get("quote") == "USDT" and m.get("type") == "swap"
        ]
        return usdt_perps[:limit]
    except Exception:
        return []


def main():
    print("Historical Data Fetcher (offline research)")
    print(f"Cache: {CACHE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
