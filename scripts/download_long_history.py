#!/usr/bin/env python3
"""Download long-history OHLCV data for all symbols/timeframes.

Usage:
    python scripts/download_long_history.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.data_engine import BingXDownloader, OHLCVValidator, DatasetRegistry, DataReport


PAIRS = [
    ("BTCUSDT", "5m"), ("BTCUSDT", "15m"), ("BTCUSDT", "30m"), ("BTCUSDT", "1h"),
    ("ETHUSDT", "15m"), ("SOLUSDT", "15m"), ("BNBUSDT", "15m"), ("XRPUSDT", "15m"),
]


def main():
    downloader = BingXDownloader()
    validator = OHLCVValidator()
    registry = DatasetRegistry()

    print("=" * 70, flush=True)
    print("  LONG-HISTORY DATA DOWNLOAD")
    print("=" * 70, flush=True)

    for symbol, tf in PAIRS:
        if downloader.file_exists(symbol, tf):
            print(f"\n  {symbol} {tf}: file exists — validating...", flush=True)
        else:
            print(f"\n  {symbol} {tf}: downloading (target 365 days)...", flush=True)
            result = downloader.download(symbol, tf, target_days=365)
            if not result.success:
                print(f"  FAILED: {result.error}", flush=True)
                continue
            print(f"  Downloaded {result.candle_count} candles, {result.days_covered} days", flush=True)

        vr = validator.validate(downloader.csv_path(symbol, tf))
        print(f"  Candles: {vr.total_candles}, Range: {vr.start_date} -> {vr.end_date}", flush=True)
        print(f"  Days: {vr.days_covered:.0f}, Missing: {vr.missing_candles}, Gaps: {vr.large_gaps}", flush=True)
        print(f"  Duplicates: {vr.duplicate_timestamps}, Invalid OHLC: {vr.invalid_ohlc}", flush=True)

        info = registry.register(symbol, tf)
        print(f"  Status: {info.quality.value} — {info.reason}", flush=True)
        print(f"  File: {info.file_path}", flush=True)

    print()
    print(DataReport.generate(registry), flush=True)


if __name__ == "__main__":
    main()
