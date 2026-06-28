import csv
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

from ultimate_trader.historical_replay.models import HistoricalCandle


BINGX_API = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "historical")
CSV_COLUMNS = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]
FALLBACK_DAY_RANGES = [365, 180, 90, 60, 30, 14, 7]


@dataclass
class DownloadResult:
    symbol: str
    timeframe: str
    candle_count: int
    days_covered: int
    start_date: str
    end_date: str
    file_path: str
    success: bool = True
    error: str = ""


class BingXDownloader:
    def __init__(self, rate_limit_s: float = 0.05):
        self._rate_limit_s = rate_limit_s
        self._last_request = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < self._rate_limit_s:
            time.sleep(self._rate_limit_s - elapsed)
        self._last_request = time.time()

    def _to_bingx_symbol(self, symbol: str) -> str:
        return symbol.replace("USDT", "-USDT")

    def _fetch_klines(self, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
        all_items = []
        cursor = start_ms
        while cursor < end_ms:
            self._rate_limit()
            resp = requests.get(BINGX_API, params={
                "symbol": symbol, "interval": interval,
                "limit": 500, "startTime": cursor,
            }, timeout=60)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            body = resp.json()
            if body.get("code") != 0:
                raise RuntimeError(f"API error {body.get('code')}: {body}")
            items = body.get("data", [])
            if not items:
                break
            all_items.extend(items)
            newest = int(items[-1]["time"])
            if newest >= end_ms:
                break
            cursor = newest + 1
        return all_items

    def _deduplicate_and_sort(self, items: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for item in items:
            ts = datetime.fromtimestamp(int(item["time"]) / 1000, tz=timezone.utc)
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            if ts_str not in seen:
                seen.add(ts_str)
                row = {
                    "timestamp": ts_str,
                    "open": item["open"],
                    "high": item["high"],
                    "low": item["low"],
                    "close": item["close"],
                    "volume": item["volume"],
                }
                result.append(row)
        result.sort(key=lambda r: r["timestamp"])
        return result

    def download(self, symbol: str, timeframe: str, target_days: int = 365) -> DownloadResult:
        api_symbol = self._to_bingx_symbol(symbol)
        error = ""
        last_items = []

        for attempt_days in [target_days] + [d for d in FALLBACK_DAY_RANGES if d != target_days]:
            try:
                now = datetime.now(timezone.utc)
                now_ms = int(now.timestamp() * 1000)
                start_ms = now_ms - attempt_days * 24 * 60 * 60 * 1000
                items = self._fetch_klines(api_symbol, timeframe, start_ms, now_ms)
                if items:
                    last_items = items
                    days_covered = attempt_days
                    break
            except Exception as e:
                error = str(e)
                continue

        if not last_items:
            return DownloadResult(
                symbol=symbol, timeframe=timeframe,
                candle_count=0, days_covered=0,
                start_date="", end_date="",
                file_path="", success=False,
                error=error or "No data returned",
            )

        rows = self._deduplicate_and_sort(last_items)
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, f"{symbol}_{timeframe}.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({
                    "symbol": symbol, "timeframe": timeframe,
                    "timestamp": r["timestamp"], "open": r["open"],
                    "high": r["high"], "low": r["low"],
                    "close": r["close"], "volume": r["volume"],
                })

        start_date = rows[0]["timestamp"] if rows else ""
        end_date = rows[-1]["timestamp"] if rows else ""
        total_days = 0
        if rows:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            total_days = (ed - sd).days

        return DownloadResult(
            symbol=symbol, timeframe=timeframe,
            candle_count=len(rows), days_covered=total_days,
            start_date=start_date, end_date=end_date,
            file_path=path, success=True,
        )

    @classmethod
    def load_candles(cls, symbol: str, timeframe: str) -> list[HistoricalCandle]:
        path = os.path.join(DATA_DIR, f"{symbol}_{timeframe}.csv")
        if not os.path.exists(path):
            return []
        candles = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    candles.append(HistoricalCandle(
                        symbol=row.get("symbol", symbol),
                        timeframe=row.get("timeframe", timeframe),
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        open=float(row["open"]), high=float(row["high"]),
                        low=float(row["low"]), close=float(row["close"]),
                        volume=float(row.get("volume", 0)),
                    ))
                except (KeyError, ValueError):
                    continue
        return candles

    @classmethod
    def csv_path(cls, symbol: str, timeframe: str) -> str:
        return os.path.join(DATA_DIR, f"{symbol}_{timeframe}.csv")

    @classmethod
    def file_exists(cls, symbol: str, timeframe: str) -> bool:
        return os.path.exists(cls.csv_path(symbol, timeframe))
