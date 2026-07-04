"""Download daily candles and funding-rate history for factor research.

Fetches from BingX public endpoints (no credentials required):
  - up to 1000 daily candles per symbol -> runtime_state/factor_data/daily/
  - up to 1000 funding records (8h) per symbol -> runtime_state/factor_data/funding/

Universe = symbols present in runtime_state/candles_cache (or top 150 by
volume from the live universe if the cache is empty).

Research only — never places orders, never enables live trading.

Usage:
    python scripts/download_factor_data.py
"""

import json, os, sys, time

import requests

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

BASE = "https://open-api.bingx.com"
CACHE = os.path.join(REPO, "runtime_state", "candles_cache")
DAILY_DIR = os.path.join(REPO, "runtime_state", "factor_data", "daily")
FUNDING_DIR = os.path.join(REPO, "runtime_state", "factor_data", "funding")


def get_universe() -> list[str]:
    if os.path.isdir(CACHE):
        syms = sorted({f.split("_")[0] for f in os.listdir(CACHE) if f.endswith(".json")})
        if syms:
            return syms
    from production_replay.bingx_universe import load_universe, is_crypto_usdt_perp
    uni = load_universe()
    contracts = [c for c in uni["contracts"] if is_crypto_usdt_perp(c.get("symbol", ""))]
    return [c["symbol"] for c in contracts[:150]]


def fetch_daily(sym: str) -> bool:
    path = os.path.join(DAILY_DIR, f"{sym}.json")
    if os.path.exists(path):
        return True
    r = requests.get(f"{BASE}/openApi/swap/v3/quote/klines",
                     params={"symbol": sym, "interval": "1d", "limit": 1000}, timeout=20)
    rows = r.json().get("data") or []
    if len(rows) < 100:
        return False
    data = sorted(({"t": int(x["time"]), "close": float(x["close"]),
                    "volume": float(x["volume"])} for x in rows), key=lambda z: z["t"])
    with open(path, "w") as f:
        json.dump(data, f)
    return True


def fetch_funding(sym: str) -> bool:
    path = os.path.join(FUNDING_DIR, f"{sym}.json")
    if os.path.exists(path):
        return True
    r = requests.get(f"{BASE}/openApi/swap/v2/quote/fundingRate",
                     params={"symbol": sym, "limit": 1000}, timeout=20)
    rows = r.json().get("data") or []
    if not rows:
        return False
    data = sorted(({"t": int(x["fundingTime"]), "rate": float(x["fundingRate"])}
                   for x in rows), key=lambda z: z["t"])
    with open(path, "w") as f:
        json.dump(data, f)
    return True


def main():
    os.makedirs(DAILY_DIR, exist_ok=True)
    os.makedirs(FUNDING_DIR, exist_ok=True)
    syms = get_universe()
    print(f"{len(syms)} symbols")
    failed = []
    for i, sym in enumerate(syms):
        try:
            ok1 = fetch_daily(sym)
            ok2 = fetch_funding(sym)
            if not (ok1 and ok2):
                failed.append(sym)
        except Exception:
            failed.append(sym)
        time.sleep(0.06)
        if (i + 1) % 25 == 0:
            print(f"[{i+1}/{len(syms)}]", flush=True)
    print(f"done, failed: {failed}")


if __name__ == "__main__":
    main()
