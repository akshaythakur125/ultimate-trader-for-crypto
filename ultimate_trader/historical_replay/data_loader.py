import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from ultimate_trader.historical_replay.models import HistoricalCandle


class HistoricalDataLoader:
    REQUIRED_COLUMNS = {"symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"}

    def __init__(self) -> None:
        self.candles: list[HistoricalCandle] = []

    def load_csv(self, file_path: str) -> list[HistoricalCandle]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        rows: list[dict[str, str]] = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError("CSV file has no header row")
            header_set = {c.strip().lower() for c in reader.fieldnames}
            if not self.REQUIRED_COLUMNS.issubset(header_set):
                missing = self.REQUIRED_COLUMNS - header_set
                raise ValueError(f"Missing required columns: {missing}")
            for row in reader:
                rows.append(row)

        parsed: list[HistoricalCandle] = []
        seen_timestamps: set[str] = set()
        for row in rows:
            ts_str = row["timestamp"].strip()
            if ts_str in seen_timestamps:
                raise ValueError(f"Duplicate timestamp: {ts_str}")
            seen_timestamps.add(ts_str)

            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    raise ValueError(f"Invalid timestamp format: {ts_str}")

            o = row["open"].strip()
            h = row["high"].strip()
            lv = row["low"].strip()
            c = row["close"].strip()
            v = row["volume"].strip()
            if not o or not h or not lv or not c or not v:
                raise ValueError(f"Missing OHLCV value at timestamp {ts_str}")

            candle = HistoricalCandle(
                symbol=row["symbol"].strip(),
                timeframe=row["timeframe"].strip(),
                timestamp=ts,
                open=float(o),
                high=float(h),
                low=float(lv),
                close=float(c),
                volume=float(v),
            )
            parsed.append(candle)

        parsed.sort(key=lambda c: c.timestamp)
        self.candles = parsed
        return self.candles

    def get_candles(
        self,
        symbol: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[HistoricalCandle]:
        result = self.candles
        if symbol:
            result = [c for c in result if c.symbol == symbol]
        if start:
            result = [c for c in result if c.timestamp >= start]
        if end:
            result = [c for c in result if c.timestamp <= end]
        return result
