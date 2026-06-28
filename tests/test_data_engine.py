import csv
import os
import tempfile
from datetime import datetime, timedelta, timezone

from ultimate_trader.data_engine.bingx_downloader import BingXDownloader, DownloadResult
from ultimate_trader.historical_replay.models import HistoricalCandle


CSV_COLUMNS = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]


class TestBingXDownloader:
    def test_csv_path_format(self):
        path = BingXDownloader.csv_path("BTCUSDT", "15m")
        assert path.endswith("BTCUSDT_15m.csv")

    def test_file_exists_returns_false_for_nonexistent(self):
        assert not BingXDownloader.file_exists("NONEXISTENT_SYMBOL", "1m")

    def test_to_bingx_symbol(self):
        d = BingXDownloader()
        assert d._to_bingx_symbol("BTCUSDT") == "BTC-USDT"
        assert d._to_bingx_symbol("ETHUSDT") == "ETH-USDT"

    def test_load_candles_empty_for_nonexistent(self):
        candles = BingXDownloader.load_candles("NONEXISTENT", "15m")
        assert candles == []

    def test_download_result_dataclass(self):
        r = DownloadResult(
            symbol="BTCUSDT", timeframe="15m", candle_count=100,
            days_covered=30, start_date="2026-01-01", end_date="2026-01-31",
            file_path="/tmp/test.csv",
        )
        assert r.symbol == "BTCUSDT"
        assert r.candle_count == 100
        assert r.success
        assert r.error == ""

    def test_download_result_failure(self):
        r = DownloadResult(
            symbol="BTCUSDT", timeframe="15m", candle_count=0,
            days_covered=0, start_date="", end_date="",
            file_path="", success=False, error="API error",
        )
        assert not r.success
        assert r.error == "API error"

    def test_deduplicate_and_sort(self):
        d = BingXDownloader()
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        items = [
            {"time": now + 60000, "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"},
            {"time": now, "open": "99", "high": "100", "low": "98", "close": "99", "volume": "10"},
            {"time": now, "open": "99", "high": "100", "low": "98", "close": "99", "volume": "10"},
        ]
        rows = d._deduplicate_and_sort(items)
        assert len(rows) == 2
        assert rows[0]["timestamp"] < rows[1]["timestamp"]

    def test_load_candles_from_csv(self, tmp_path):
        csv_path = os.path.join(tmp_path, "test.csv")
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            w.writerow({"symbol": "BTCUSDT", "timeframe": "15m",
                        "timestamp": "2026-01-01 00:00:00",
                        "open": "100", "high": "101", "low": "99",
                        "close": "100.5", "volume": "1000"})
        candles = []
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    candles.append(HistoricalCandle(
                        symbol=row.get("symbol", "BTCUSDT"),
                        timeframe=row.get("timeframe", "15m"),
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        open=float(row["open"]), high=float(row["high"]),
                        low=float(row["low"]), close=float(row["close"]),
                        volume=float(row.get("volume", 0)),
                    ))
                except (KeyError, ValueError):
                    continue
        assert len(candles) == 1
        assert candles[0].symbol == "BTCUSDT"
        assert candles[0].close == 100.5
