from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Optional

from ultimate_trader.regime_filter.regime_classifier import (
    FEATURE_NAMES,
    RegimeFeatures,
)


@dataclass
class ReferenceProfile:
    num_samples: int = 0
    sorted_vals: dict[str, list[float]] = field(default_factory=dict)

    @staticmethod
    def from_features(features: list[RegimeFeatures]) -> "ReferenceProfile":
        if not features:
            return ReferenceProfile()
        n = len(features)
        vals: dict[str, list[float]] = {f: [] for f in FEATURE_NAMES}
        for rf in features:
            for f in FEATURE_NAMES:
                vals[f].append(getattr(rf, f))
        sorted_vals = {}
        for f in FEATURE_NAMES:
            sorted_vals[f] = sorted(vals[f])
        return ReferenceProfile(num_samples=n, sorted_vals=sorted_vals)


def _percentile(val: float, sorted_dist: list[float]) -> float:
    """Percentile rank (0-100) of val within sorted distribution.
    Uses average of bisect_left and bisect_right so duplicates map to 50%."""
    if not sorted_dist:
        return 50.0
    n = len(sorted_dist)
    left = bisect_left(sorted_dist, val)
    right = bisect_right(sorted_dist, val)
    return ((left + right) / 2.0) / n * 100.0


def _percentile_similarity(val: float, sorted_dist: list[float]) -> float:
    """How close val's percentile is to 50% (median). 100=at median, 0=at edge."""
    pct = _percentile(val, sorted_dist)
    return max(0.0, 100.0 - 2.0 * abs(50.0 - pct))


class SimilarityScorer:
    def __init__(self, reference: Optional[ReferenceProfile] = None):
        self._ref = reference

    @property
    def has_reference(self) -> bool:
        return self._ref is not None and self._ref.num_samples > 0

    def set_reference(self, reference: ReferenceProfile):
        self._ref = reference

    def score(self, features: RegimeFeatures) -> float:
        if not self.has_reference or self._ref is None:
            return 100.0
        n_ok = 0
        total = 0
        for f in FEATURE_NAMES:
            val = getattr(features, f)
            dist = self._ref.sorted_vals.get(f, [])
            feat_sim = _percentile_similarity(val, dist)
            total += feat_sim
            n_ok += 1
        return round(total / n_ok, 1) if n_ok > 0 else 100.0
