import os
import tempfile

from ultimate_trader.data_engine.ohlcv_validator import OHLCVValidator, REQUIRED_COLUMNS


CSV_HEADER = "symbol,timeframe,timestamp,open,high,low,close,volume"


class TestOHLCVValidator:
    def _write_csv(self, tmp_path, rows: list[str]) -> str:
        path = os.path.join(tmp_path, "test.csv")
        with open(path, "w", newline="") as f:
            f.write(CSV_HEADER + "\n")
            for r in rows:
                f.write(r + "\n")
        return path

    def test_valid_csv(self, tmp_path):
        rows = [
            "BTCUSDT,15m,2026-01-01 00:00:00,100,101,99,100.5,1000",
            "BTCUSDT,15m,2026-01-01 00:15:00,100.5,102,100,101,1200",
            "BTCUSDT,15m,2026-01-01 00:30:00,101,103,100,102,1100",
        ]
        path = self._write_csv(tmp_path, rows)
        v = OHLCVValidator()
        r = v.validate(path)
        assert r.valid
        assert r.total_candles == 3
        assert r.duplicate_timestamps == 0
        assert r.non_monotonic_timestamps == 0
        assert r.invalid_ohlc == 0

    def test_catches_duplicate_timestamps(self, tmp_path):
        rows = [
            "BTCUSDT,15m,2026-01-01 00:00:00,100,101,99,100.5,1000",
            "BTCUSDT,15m,2026-01-01 00:00:00,100,101,99,100.5,1000",
        ]
        path = self._write_csv(tmp_path, rows)
        v = OHLCVValidator()
        r = v.validate(path)
        assert r.duplicate_timestamps == 1

    def test_catches_gaps(self, tmp_path):
        rows = [
            "BTCUSDT,15m,2026-01-01 00:00:00,100,101,99,100.5,1000",
            "BTCUSDT,15m,2026-01-01 01:00:00,101,102,100,101,1200",
        ]
        path = self._write_csv(tmp_path, rows)
        v = OHLCVValidator()
        r = v.validate(path)
        assert r.large_gaps >= 1
        assert r.missing_candles >= 3

    def test_catches_invalid_ohlc(self, tmp_path):
        rows = [
            "BTCUSDT,15m,2026-01-01 00:00:00,100,99,98,100,1000",
            "BTCUSDT,15m,2026-01-01 00:15:00,100,101,102,100,1000",
        ]
        path = self._write_csv(tmp_path, rows)
        v = OHLCVValidator()
        r = v.validate(path)
        assert r.invalid_ohlc >= 1

    def test_catches_non_monotonic_timestamps(self, tmp_path):
        rows = [
            "BTCUSDT,15m,2026-01-01 00:15:00,100,101,99,100.5,1000",
            "BTCUSDT,15m,2026-01-01 00:00:00,100,101,99,100.5,1000",
        ]
        path = self._write_csv(tmp_path, rows)
        v = OHLCVValidator()
        r = v.validate(path)
        assert r.non_monotonic_timestamps == 1

    def test_reports_missing_file(self):
        v = OHLCVValidator()
        r = v.validate("/nonexistent/path.csv")
        assert not r.valid
        assert "not found" in r.errors[0].lower()

    def test_reports_empty_file(self, tmp_path):
        path = os.path.join(tmp_path, "empty.csv")
        with open(path, "w") as f:
            f.write(CSV_HEADER + "\n")
        v = OHLCVValidator()
        r = v.validate(path)
        assert not r.valid or r.total_candles == 0

    def test_required_columns_exist(self, tmp_path):
        path = os.path.join(tmp_path, "bad.csv")
        with open(path, "w") as f:
            f.write("a,b,c\n1,2,3\n")
        v = OHLCVValidator()
        r = v.validate(path)
        assert not r.valid

    def test_zero_volume_detected(self, tmp_path):
        rows = [
            "BTCUSDT,15m,2026-01-01 00:00:00,100,101,99,100.5,0",
            "BTCUSDT,15m,2026-01-01 00:15:00,101,102,100,101,0",
            "BTCUSDT,15m,2026-01-01 00:30:00,102,103,101,102,0",
        ]
        path = self._write_csv(tmp_path, rows)
        v = OHLCVValidator()
        r = v.validate(path)
        assert r.zero_volume_candles == 3
