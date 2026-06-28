from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle
from ultimate_trader.regime_filter.regime_classifier import (
    FEATURE_NAMES,
    RegimeClassifier,
    RegimeFeatures,
)
from ultimate_trader.regime_filter.regime_similarity import (
    ReferenceProfile,
    SimilarityScorer,
)



@dataclass
class RegimeGateConfig:
    similarity_threshold: float = 50.0
    reference_window_candles: int = 2880


@dataclass
class RegimeGateDecision:
    allowed: bool = True
    similarity_score: float = 100.0
    rejection_reason: str = ""
    features: Optional[RegimeFeatures] = None


class RegimeGate:
    def __init__(self, config: Optional[RegimeGateConfig] = None):
        self._cfg = config or RegimeGateConfig()
        self._classifier = RegimeClassifier()
        self._scorer = SimilarityScorer()
        self._ref_built = False

    @property
    def is_trained(self) -> bool:
        return self._ref_built

    def fit(self, training_candles: list[HistoricalCandle]):
        from ultimate_trader.robustness_lab.replay_runner import _LsmPipeline
        lsm_pipeline = _LsmPipeline()
        all_features: list[RegimeFeatures] = []
        window = self._cfg.reference_window_candles
        if window > 0 and len(training_candles) > window:
            training_candles = training_candles[-window:]
        for candle in training_candles:
            lsm_data, conf_result = lsm_pipeline.process_candle(candle)
            features = self._classifier.compute(candle, lsm_data, conf_result)
            all_features.append(features)
        profile = ReferenceProfile.from_features(all_features)
        self._scorer.set_reference(profile)
        self._ref_built = True

    def check(self, candle, lsm_data: dict, conf_result) -> RegimeGateDecision:
        if not self._ref_built:
            return RegimeGateDecision(allowed=True, similarity_score=100.0)
        features = self._classifier.compute(candle, lsm_data, conf_result)
        sim = self._scorer.score(features)
        if sim < self._cfg.similarity_threshold:
            return RegimeGateDecision(
                allowed=False,
                similarity_score=sim,
                rejection_reason=f"Regime similarity {sim:.1f} < {self._cfg.similarity_threshold}",
                features=features,
            )
        return RegimeGateDecision(
            allowed=True,
            similarity_score=sim,
            features=features,
        )

    def reset_classifier(self):
        self._classifier.reset()

    def reset(self):
        self._classifier.reset()
        self._scorer = SimilarityScorer()
        self._ref_built = False
