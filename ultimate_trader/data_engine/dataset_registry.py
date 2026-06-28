import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ultimate_trader.data_engine.ohlcv_validator import OHLCVValidator


class QualityStatus(str, Enum):
    GOOD = "GOOD"
    ACCEPTABLE_WITH_GAPS = "ACCEPTABLE_WITH_GAPS"
    BAD = "BAD"
    TOO_SHORT = "TOO_SHORT"


@dataclass
class DatasetInfo:
    symbol: str
    timeframe: str
    file_path: str
    candle_count: int
    days_covered: float
    start_date: str
    end_date: str
    quality: QualityStatus
    reason: str = ""
    missing_candles: int = 0
    duplicate_timestamps: int = 0
    large_gaps: int = 0
    invalid_ohlc: int = 0
    zero_volume_candles: int = 0

    @property
    def available(self) -> bool:
        return self.candle_count > 0 and self.quality in (QualityStatus.GOOD, QualityStatus.ACCEPTABLE_WITH_GAPS)


DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "historical")


class DatasetRegistry:
    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = data_dir or DEFAULT_DATA_DIR
        self._datasets: list[DatasetInfo] = []

    @property
    def datasets(self) -> list[DatasetInfo]:
        return list(self._datasets)

    def register(self, symbol: str, timeframe: str) -> DatasetInfo:
        path = os.path.join(self._data_dir, f"{symbol}_{timeframe}.csv")
        validator = OHLCVValidator()
        vr = validator.validate(path)
        quality, reason = self._classify(vr)
        info = DatasetInfo(
            symbol=symbol, timeframe=timeframe,
            file_path=vr.file_path, candle_count=vr.total_candles,
            days_covered=vr.days_covered,
            start_date=vr.start_date, end_date=vr.end_date,
            quality=quality, reason=reason,
            missing_candles=vr.missing_candles,
            duplicate_timestamps=vr.duplicate_timestamps,
            large_gaps=vr.large_gaps,
            invalid_ohlc=vr.invalid_ohlc,
            zero_volume_candles=vr.zero_volume_candles,
        )
        self._datasets.append(info)
        return info

    def get(self, symbol: str, timeframe: str) -> Optional[DatasetInfo]:
        for d in self._datasets:
            if d.symbol == symbol and d.timeframe == timeframe:
                return d
        return None

    def _classify(self, vr) -> tuple[QualityStatus, str]:
        if not vr.valid or vr.total_candles == 0:
            return QualityStatus.BAD, vr.errors[0] if vr.errors else "Invalid dataset"
        if vr.total_candles < 100:
            return QualityStatus.TOO_SHORT, f"Only {vr.total_candles} candles (need >= 100)"
        reasons = []
        if vr.duplicate_timestamps > 0:
            reasons.append(f"{vr.duplicate_timestamps} duplicates")
        if vr.non_monotonic_timestamps > 0:
            reasons.append(f"{vr.non_monotonic_timestamps} non-monotonic")
        if vr.invalid_ohlc > 0:
            reasons.append(f"{vr.invalid_ohlc} invalid OHLC")
        gap_ratio = vr.missing_candles / max(vr.total_candles, 1)
        if gap_ratio > 0.2:
            return QualityStatus.BAD, f"Excessive gaps: {vr.missing_candles} missing ({gap_ratio:.0%})"
        if gap_ratio > 0.05:
            reasons.append(f"{vr.missing_candles} missing candles ({gap_ratio:.1%})")
            return QualityStatus.ACCEPTABLE_WITH_GAPS, "; ".join(reasons)
        if reasons:
            return QualityStatus.ACCEPTABLE_WITH_GAPS, "; ".join(reasons)
        return QualityStatus.GOOD, "OK"
