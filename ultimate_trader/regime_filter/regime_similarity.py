from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Optional

from ultimate_trader.regime_filter.regime_classifier import (
    FEATURE_NAMES,
    RegimeFeatures,
)

FEATURE_RANGES = {
    "norm_volatility": (0.0, 0.05),
    "volume_ratio": (0.0, 5.0),
    "sweep_intensity": (0.0, 1.0),
    "trend_strength": (0.0, 1.0),
    "orderflow_strength": (0.0, 1.0),
    "microstructure_strength": (0.0, 1.0),
    "directional_confidence": (0.0, 1.0),
    "conflict_score": (0.0, 1.0),
    "confluence_score": (0.0, 100.0),
    "structure_event_count": (0.0, 10.0),
}


@dataclass
class ReferenceProfile:
    num_samples: int = 0
    means: dict[str, float] = field(default_factory=dict)
    stds: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def from_features(features: list[RegimeFeatures]) -> "ReferenceProfile":
        if not features:
            return ReferenceProfile()
        n = len(features)
        vals: dict[str, list[float]] = {f: [] for f in FEATURE_NAMES}
        for rf in features:
            for f in FEATURE_NAMES:
                vals[f].append(getattr(rf, f))
        means = {}
        stds = {}
        for f in FEATURE_NAMES:
            v = vals[f]
            low, high = FEATURE_RANGES[f]
            clipped = [max(low, min(high, x)) for x in v]
            means[f] = mean(clipped)
            stds[f] = stdev(clipped) if len(clipped) >= 2 and stdev(clipped) > 0 else (high - low) * 0.1
        return ReferenceProfile(num_samples=n, means=means, stds=stds)


class SimilarityScorer:
    def __init__(self, reference: Optional[ReferenceProfile] = None):
        self._ref = reference

    @property
    def has_reference(self) -> bool:
        return self._ref is not None and self._ref.num_samples > 0

    def set_reference(self, reference: ReferenceProfile):
        self._ref = reference

    def score(self, features: RegimeFeatures) -> float:
        if not self.has_reference:
            return 100.0
        if self._ref is None:
            return 100.0
        n_ok = 0
        total = 0
        for f in FEATURE_NAMES:
            val = getattr(features, f)
            ref_mean = self._ref.means.get(f, 0)
            ref_std = self._ref.stds.get(f, 1)
            z = (val - ref_mean) / ref_std if ref_std > 0 else 0
            z_clip = max(-3.0, min(3.0, z))
            feat_sim = max(0.0, 100.0 - abs(z_clip) * 33.33)
            total += feat_sim
            n_ok += 1
        return round(total / n_ok, 1) if n_ok > 0 else 100.0
