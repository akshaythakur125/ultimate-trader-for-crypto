import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests


CSV_COLUMNS = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "historical", "BTCUSDT_15m.csv")
BINGX_API = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"


def fetch_klines(symbol: str, interval: str, days: int = 30):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = now_ms - days * 24 * 60 * 60 * 1000
    all_items = []
    cursor = start_ms
    batch_size = 500

    while cursor < now_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": batch_size,
            "startTime": cursor,
        }
        resp = requests.get(BINGX_API, params=params, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"API error {body.get('code')}: {body.get('msg', body)}")
        items = body.get("data", [])
        if not items:
            break
        all_items.extend(items)
        # API returns newest first — track the newest time to advance cursor
        newest_time = items[0]["time"]
        if newest_time >= now_ms:
            break
        cursor = newest_time + 1

    return all_items


def items_to_csv(items, symbol: str, timeframe: str, output_path: str):
    seen = set()
    rows = []
    for item in items:
        ts = datetime.fromtimestamp(item["time"] / 1000, tz=timezone.utc)
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        if ts_str in seen:
            continue
        seen.add(ts_str)
        rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": ts_str,
            "open": item["open"],
            "high": item["high"],
            "low": item["low"],
            "close": item["close"],
            "volume": item["volume"],
        })
    rows.sort(key=lambda r: r["timestamp"])

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main():
    print("=" * 60)
    print("Ultimate Trader — BingX OHLCV Downloader")
    print("=" * 60)

    api_symbol = "BTC-USDT"
    csv_symbol = "BTCUSDT"
    timeframe = "15m"
    days = 30

    print(f"\nFetching {api_symbol} {timeframe} data for the last {days} days...")
    print(f"Endpoint: GET {BINGX_API}")
    print(f"(public API — no API key required)\n")

    try:
        items = fetch_klines(api_symbol, timeframe, days=days)
    except Exception as e:
        print(f"Error fetching data from BingX API: {e}")
        sys.exit(1)

    if not items:
        print("No klines returned from BingX API.")
        sys.exit(1)

    print(f"Raw klines fetched: {len(items)}")

    output_path = os.path.abspath(OUTPUT_PATH)
    count = items_to_csv(items, csv_symbol, timeframe, output_path)

    print(f"CSV rows written: {count}")
    print(f"Output: {output_path}")
    times = sorted(item["time"] for item in items)
    print(f"Date range: "
          f"{datetime.fromtimestamp(times[0] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} → "
          f"{datetime.fromtimestamp(times[-1] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    print("Done.")


if __name__ == "__main__":
    main()
