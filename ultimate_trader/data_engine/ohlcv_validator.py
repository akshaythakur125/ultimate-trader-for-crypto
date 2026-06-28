import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "1h": 60}
REQUIRED_COLUMNS = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]


@dataclass
class ValidationResult:
    file_path: str
    valid: bool = True
    total_candles: int = 0
    start_date: str = ""
    end_date: str = ""
    days_covered: float = 0.0
    duplicate_timestamps: int = 0
    missing_candles: int = 0
    large_gaps: int = 0
    invalid_ohlc: int = 0
    zero_volume_candles: int = 0
    non_monotonic_timestamps: int = 0
    expected_spacing_minutes: int = 0
    errors: list[str] = field(default_factory=list)


class OHLCVValidator:
    def validate(self, file_path: str) -> ValidationResult:
        result = ValidationResult(file_path=file_path)
        if not os.path.exists(file_path):
            result.valid = False
            result.errors.append("File not found")
            return result

        rows = []
        with open(file_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        result.total_candles = len(rows)
        if not rows:
            result.valid = False
            result.errors.append("Empty file")
            return result

        first_row = rows[0]
        if not all(col in first_row for col in REQUIRED_COLUMNS):
            missing = [c for c in REQUIRED_COLUMNS if c not in first_row]
            result.errors.append(f"Missing columns: {missing}")
            result.valid = False
            return result

        try:
            tf = first_row.get("timeframe", "")
            result.expected_spacing_minutes = TIMEFRAME_MINUTES.get(tf, 15)
        except Exception:
            pass

        timestamps = []
        prev_ts: Optional[datetime] = None
        seen_timestamps = set()

        for row in rows:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
            except (ValueError, KeyError):
                result.invalid_ohlc += 1
                continue

            timestamps.append(ts)

            if ts in seen_timestamps:
                result.duplicate_timestamps += 1
            seen_timestamps.add(ts)

            if prev_ts is not None and ts < prev_ts:
                result.non_monotonic_timestamps += 1
            prev_ts = ts

            try:
                o, h, l, c, v = (
                    float(row["open"]), float(row["high"]),
                    float(row["low"]), float(row["close"]),
                    float(row.get("volume", 0)),
                )
                if h < l or c < l or c > h or o < l or o > h:
                    result.invalid_ohlc += 1
                if v == 0:
                    result.zero_volume_candles += 1
            except (ValueError, KeyError):
                result.invalid_ohlc += 1

        if timestamps:
            result.start_date = timestamps[0].strftime("%Y-%m-%d")
            result.end_date = timestamps[-1].strftime("%Y-%m-%d")
            result.days_covered = (timestamps[-1] - timestamps[0]).total_seconds() / 86400

        spacing = timedelta(minutes=result.expected_spacing_minutes)
        for i in range(1, len(timestamps)):
            diff = (timestamps[i] - timestamps[i - 1]).total_seconds()
            expected_seconds = spacing.total_seconds()
            if diff > expected_seconds * 2:
                result.large_gaps += 1
                gap_candles = int(round(diff / expected_seconds)) - 1
                result.missing_candles += gap_candles

        expected_total = int(round(result.days_covered * 24 * 60 / result.expected_spacing_minutes))
        actual_total = result.total_candles
        calculated_missing = max(0, expected_total - actual_total)
        if calculated_missing > result.missing_candles:
            result.missing_candles = calculated_missing

        if result.duplicate_timestamps > 0:
            result.errors.append(f"{result.duplicate_timestamps} duplicate timestamps")
        if result.non_monotonic_timestamps > 0:
            result.errors.append(f"{result.non_monotonic_timestamps} non-monotonic timestamps")
        if result.large_gaps > 0:
            result.errors.append(f"{result.large_gaps} large gaps ({result.missing_candles} total missing candles)")
        if result.invalid_ohlc > 0:
            result.errors.append(f"{result.invalid_ohlc} invalid OHLC values")
        if result.zero_volume_candles > 0 and result.zero_volume_candles > result.total_candles * 0.1:
            result.errors.append(f"{result.zero_volume_candles} zero-volume candles (>10%)")
        if result.total_candles < 100:
            result.errors.append(f"Too few candles: {result.total_candles}")

        return result
