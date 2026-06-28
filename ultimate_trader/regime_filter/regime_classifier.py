from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean
from typing import Any, Optional


@dataclass
class RegimeFeatures:
    timestamp: datetime
    norm_volatility: float
    volume_ratio: float
    sweep_intensity: float
    trend_strength: float
    orderflow_strength: float
    microstructure_strength: float
    directional_confidence: float
    conflict_score: float
    confluence_score: float
    structure_event_count: int


FEATURE_NAMES = [
    "norm_volatility", "volume_ratio", "sweep_intensity",
    "trend_strength", "orderflow_strength", "microstructure_strength",
    "directional_confidence", "conflict_score", "confluence_score",
    "structure_event_count",
]


class RegimeClassifier:
    def __init__(self, window: int = 20):
        self._window = window
        self._ranges: list[float] = []
        self._volumes: list[float] = []

    def compute(self, candle, lsm_data: dict, conf_result) -> RegimeFeatures:
        candle_range = candle.high - candle.low
        norm_vol = candle_range / candle.close if candle.close > 0 else 0.0

        self._ranges.append(candle_range)
        self._volumes.append(candle.volume)
        if len(self._ranges) > self._window:
            self._ranges.pop(0)
            self._volumes.pop(0)

        avg_range = mean(self._ranges) if self._ranges else candle_range
        avg_volume = mean(self._volumes) if self._volumes else candle.volume
        range_ratio = candle_range / avg_range if avg_range > 0 else 1.0
        volume_ratio = candle.volume / avg_volume if avg_volume > 0 else 1.0

        sweeps = lsm_data.get("sweeps", [])
        sweep_intensity = min(len(sweeps) / 5.0, 1.0)

        trend_strength = abs(lsm_data.get("trend_bias", 0))
        orderflow_strength = abs(lsm_data.get("orderflow_bias", 0))
        microstructure_strength = abs(lsm_data.get("microstructure_bias", 0))
        directional_confidence = conf_result.directional_confidence
        conflict_score = conf_result.conflict_score
        confluence_score = lsm_data.get("confluence_score", 0)
        struct_events = lsm_data.get("structure_events", [])
        struct_count = len(struct_events) if struct_events else 0

        return RegimeFeatures(
            timestamp=candle.timestamp,
            norm_volatility=round(norm_vol, 6),
            volume_ratio=round(volume_ratio, 4),
            sweep_intensity=round(sweep_intensity, 4),
            trend_strength=round(trend_strength, 4),
            orderflow_strength=round(orderflow_strength, 4),
            microstructure_strength=round(microstructure_strength, 4),
            directional_confidence=round(directional_confidence, 4),
            conflict_score=round(conflict_score, 4),
            confluence_score=round(confluence_score, 2),
            structure_event_count=struct_count,
        )

    def reset(self):
        self._ranges.clear()
        self._volumes.clear()
