"""
Phase 79 — Derivatives Data Collector
Collects live derivatives data from BingX for active symbols:
  - Price, volume, 24h stats (via swap ticker)
  - Funding rate (via /fundingRate endpoint)
  - Open interest (via /openInterest endpoint)
Appends to runtime_state/derivatives_observations.jsonl
Never fakes missing data.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bingx_client import get_all_swap_tickers

RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
OBS_FILE = os.path.join(RUNTIME_DIR, "derivatives_observations.jsonl")

# BingX public endpoints (no auth required)
BINGX_BASE = "https://open-api.bingx.com"

# Known USDT perpetual symbols to always try (top liquid symbols)
FALLBACK_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT",
    "ADA-USDT", "AVAX-USDT", "LINK-USDT", "DOT-USDT", "MATIC-USDT",
    "UNI-USDT", "SHIB-USDT", "LTC-USDT", "BCH-USDT", "ATOM-USDT",
    "APT-USDT", "ARB-USDT", "OP-USDT", "SUI-USDT", "NEAR-USDT",
    "FIL-USDT", "IMX-USDT", "RENDER-USDT", "INJ-USDT", "TIA-USDT",
    "WLD-USDT", "PEPE-USDT", "FET-USDT", "SEI-USDT", "JUP-USDT",
    "BONK-USDT", "WIF-USDT", "ORDI-USDT", "STX-USDT", "FLOKI-USDT",
]

# Symbols that are known to have derivatives data on BingX
DERIVATIVES_ENABLED = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT",
    "ADA-USDT", "AVAX-USDT", "LINK-USDT", "DOT-USDT", "MATIC-USDT",
    "UNI-USDT", "SHIB-USDT", "LTC-USDT", "BCH-USDT", "ATOM-USDT",
    "APT-USDT", "ARB-USDT", "OP-USDT", "SUI-USDT", "NEAR-USDT",
    "FIL-USDT", "IMX-USDT", "RENDER-USDT", "INJ-USDT", "TIA-USDT",
    "WLD-USDT", "PEPE-USDT", "FET-USDT", "SEI-USDT", "JUP-USDT",
    "BONK-USDT", "WIF-USDT", "ORDI-USDT", "STX-USDT", "FLOKI-USDT",
]


def _public_get(path, params=None):
    """Make a public GET request to BingX."""
    import requests
    url = f"{BINGX_BASE}{path}"
    try:
        resp = requests.get(url, params=params or {}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fetch_funding_rate(symbol):
    """Fetch current funding rate for a symbol.
    Returns dict with fundingRate and nextFundingTime, or None if unavailable.
    BingX endpoint: /openApi/swap/v2/quote/fundingRate
    """
    result = _public_get(
        "/openApi/swap/v2/quote/fundingRate",
        {"symbol": symbol}
    )
    if not result["success"]:
        return None
    data = result.get("data", {})
    if not data or "data" not in data:
        return None
    funding_data = data["data"]
    if not funding_data:
        return None
    latest = funding_data[0] if isinstance(funding_data, list) else funding_data
    return {
        "fundingRate": latest.get("fundingRate"),
        "nextFundingTime": latest.get("nextFundingTime"),
        "symbol": symbol,
    }


def fetch_open_interest(symbol):
    """Fetch current open interest for a symbol.
    Returns dict with openInterest and value, or None if unavailable.
    BingX endpoint: /openApi/swap/v2/quote/openInterest
    """
    result = _public_get(
        "/openApi/swap/v2/quote/openInterest",
        {"symbol": symbol}
    )
    if not result["success"]:
        return None
    data = result.get("data", {})
    if not data or "data" not in data:
        return None
    oi_data = data["data"]
    if not oi_data:
        return None
    return {
        "openInterest": oi_data.get("openInterest"),
        "sumValue": oi_data.get("sumValue"),
        "symbol": symbol,
    }


def collect_derivatives_data(max_symbols=50):
    """Collect derivatives data for top symbols.
    Returns list of observation dicts.
    """
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    observations = []
    timestamp = datetime.now(timezone.utc).isoformat()

    # Get all swap tickers for volume ranking
    all_tickers = get_all_swap_tickers()
    if not all_tickers:
        print("[derivatives_data_collector] WARNING: Could not fetch swap tickers")
        return observations

    # Filter to USDT perpetuals and rank by volume
    usdt_swap = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if sym.endswith("-USDT") and not sym.endswith("_USDT"):
            vol = float(t.get("volume", 0) or 0)
            usdt_swap.append((sym, vol, t))

    usdt_swap.sort(key=lambda x: x[1], reverse=True)
    top_symbols = usdt_swap[:max_symbols]

    collected = 0
    errors = 0

    for sym, vol, ticker_data in top_symbols:
        # Basic price/volume data (always available)
        price = float(ticker_data.get("lastPrice", 0) or 0)
        high_24h = float(ticker_data.get("highPrice", 0) or 0)
        low_24h = float(ticker_data.get("lowPrice", 0) or 0)
        change_24h = float(ticker_data.get("priceChangePercent", 0) or 0)

        # Funding rate (may be unavailable)
        funding = fetch_funding_rate(sym)
        funding_rate = None
        funding_available = False
        if funding and funding.get("fundingRate") is not None:
            try:
                funding_rate = float(funding["fundingRate"])
                funding_available = True
            except (ValueError, TypeError):
                pass

        # Open interest (may be unavailable)
        oi = fetch_open_interest(sym)
        oi_value = None
        oi_available = False
        if oi and oi.get("openInterest") is not None:
            try:
                oi_value = float(oi["openInterest"])
                oi_available = True
            except (ValueError, TypeError):
                pass

        obs = {
            "symbol": sym,
            "timestamp": timestamp,
            "price": price,
            "volume_24h": vol,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "change_24h_pct": change_24h,
            "funding_rate": funding_rate,
            "funding_available": funding_available,
            "open_interest": oi_value,
            "oi_available": oi_available,
        }

        observations.append(obs)
        collected += 1

        # Rate limit: 50ms between derivative calls
        if funding_available or oi_available:
            time.sleep(0.05)

    print(f"[derivatives_data_collector] Collected {collected} observations, {errors} errors")

    # Append to JSONL
    with open(OBS_FILE, "a", encoding="utf-8") as f:
        for obs in observations:
            f.write(json.dumps(obs) + "\n")

    return observations


def get_latest_observations(symbol=None, limit=100):
    """Read latest observations from JSONL file.
    If symbol specified, filter to that symbol.
    Returns list of dicts.
    """
    if not os.path.exists(OBS_FILE):
        return []
    observations = []
    with open(OBS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obs = json.loads(line)
                if symbol and obs.get("symbol") != symbol:
                    continue
                observations.append(obs)
            except json.JSONDecodeError:
                continue
    # Return most recent
    return observations[-limit:]


def get_oi_funding_summary(symbol):
    """Get latest OI and funding for a specific symbol.
    Returns dict with oi_latest, oi_prev, funding_latest, funding_prev.
    """
    obs = get_latest_observations(symbol, limit=10)
    if len(obs) < 1:
        return {
            "oi_latest": None, "oi_prev": None,
            "funding_latest": None, "funding_prev": None,
            "oi_available": False, "funding_available": False,
        }
    latest = obs[-1]
    prev = obs[-2] if len(obs) >= 2 else None
    return {
        "oi_latest": latest.get("open_interest"),
        "oi_prev": prev.get("open_interest") if prev else None,
        "funding_latest": latest.get("funding_rate"),
        "funding_prev": prev.get("funding_rate") if prev else None,
        "oi_available": latest.get("oi_available", False),
        "funding_available": latest.get("funding_available", False),
        "price": latest.get("price"),
        "volume_24h": latest.get("volume_24h"),
    }


def _get_observations_count():
    """Count lines in observations JSONL."""
    if not os.path.exists(OBS_FILE):
        return 0
    with open(OBS_FILE, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


if __name__ == "__main__":
    print("=" * 60)
    print("DERIVATIVES DATA COLLECTOR")
    print("=" * 60)
    obs = collect_derivatives_data(max_symbols=30)
    print(f"\nCollected {len(obs)} observations")
    available_oi = sum(1 for o in obs if o.get("oi_available"))
    available_fr = sum(1 for o in obs if o.get("funding_available"))
    print(f"  OI available: {available_oi}/{len(obs)}")
    print(f"  Funding available: {available_fr}/{len(obs)}")
    total = _get_observations_count()
    print(f"  Total observations in file: {total}")
