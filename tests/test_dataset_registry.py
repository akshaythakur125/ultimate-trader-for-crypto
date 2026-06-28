import os
import csv

from ultimate_trader.data_engine.dataset_registry import DatasetRegistry, QualityStatus


def _create_csv(path: str, rows: int, timeframe: str = "15m"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"])
        base = 100
        for i in range(rows):
            ts = f"2026-01-{i//96+1:02d} {(i%96)*15//60:02d}:{(i%96)*15%60:02d}:00"
            w.writerow(["BTCUSDT", timeframe, ts, str(base), str(base+1),
                       str(base-1), str(base+0.5), "1000"])
            base += 0.5


class TestDatasetRegistry:
    def test_good_dataset(self, tmp_path):
        csv_path = os.path.join(str(tmp_path), "BTCUSDT_15m.csv")
        _create_csv(csv_path, 500)
        reg = DatasetRegistry(data_dir=str(tmp_path))
        info = reg.register("BTCUSDT", "15m")
        assert info.quality == QualityStatus.GOOD
        assert info.candle_count == 500
        assert info.available

    def test_too_short_dataset(self, tmp_path):
        csv_path = os.path.join(str(tmp_path), "BTCUSDT_15m.csv")
        _create_csv(csv_path, 50)
        reg = DatasetRegistry(data_dir=str(tmp_path))
        info = reg.register("BTCUSDT", "15m")
        assert info.quality == QualityStatus.TOO_SHORT
        assert not info.available

    def test_bad_missing_file(self, tmp_path):
        reg = DatasetRegistry(data_dir=str(tmp_path))
        info = reg.register("NONEXISTENT", "15m")
        assert info.quality == QualityStatus.BAD
        assert info.candle_count == 0
        assert not info.available

    def test_duplicate_detection(self, tmp_path):
        csv_path = os.path.join(str(tmp_path), "BTCUSDT_15m.csv")
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"])
            w.writerow(["BTCUSDT", "15m", "2026-01-01 00:00:00", "100", "101", "99", "100.5", "1000"])
            w.writerow(["BTCUSDT", "15m", "2026-01-01 00:00:00", "100", "101", "99", "100.5", "1000"])
        reg = DatasetRegistry(data_dir=str(tmp_path))
        info = reg.register("BTCUSDT", "15m")
        assert info.duplicate_timestamps > 0

    def test_get_returns_none_for_unregistered(self):
        reg = DatasetRegistry()
        assert reg.get("BTCUSDT", "15m") is None

    def test_get_returns_registered(self, tmp_path):
        csv_path = os.path.join(str(tmp_path), "BTCUSDT_15m.csv")
        _create_csv(csv_path, 200)
        reg = DatasetRegistry(data_dir=str(tmp_path))
        reg.register("BTCUSDT", "15m")
        info = reg.get("BTCUSDT", "15m")
        assert info is not None
        assert info.symbol == "BTCUSDT"
        assert info.timeframe == "15m"

    def test_datasets_property(self, tmp_path):
        csv_path = os.path.join(str(tmp_path), "BTCUSDT_15m.csv")
        _create_csv(csv_path, 200)
        reg = DatasetRegistry(data_dir=str(tmp_path))
        reg.register("BTCUSDT", "15m")
        assert len(reg.datasets) == 1
