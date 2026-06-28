import pytest
import random
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from ultimate_trader.historical_replay.models import HistoricalCandle
from ultimate_trader.liquidity_smart_money import Candle as LsmCandle, ConfluenceResult, DirectionalBias
from ultimate_trader.regime_filter.regime_classifier import RegimeClassifier, RegimeFeatures, FEATURE_NAMES
from ultimate_trader.regime_filter.regime_similarity import ReferenceProfile, SimilarityScorer
from ultimate_trader.regime_filter.regime_gate import RegimeGate, RegimeGateConfig, RegimeGateDecision


def make_candle(timestamp=None, symbol="BTCUSDT", open_p=50000, high=50500, low=49500, close=50000, volume=100):
    return HistoricalCandle(
        symbol=symbol, timeframe="15m",
        timestamp=timestamp or datetime(2024, 1, 1, 0, 0),
        open=open_p, high=high, low=low, close=close, volume=volume,
    )


def make_lsm_data(sweeps=1, trend_bias=0.5, orderflow_bias=0.0, microstructure_bias=0.0,
                  confluence_score=50, direction="LONG"):
    return {
        "direction": direction, "confluence_score": confluence_score,
        "trade_permission": "ALLOW",
        "swing_highs": [], "swing_lows": [], "sweeps": [{}] * sweeps,
        "structure_events": [], "fvgs": [], "order_blocks": [],
        "risk_score": 0.0,
        "sweep_bias": 1.0, "structure_bias": 1.0,
        "fvg_bias": 0.5, "order_block_bias": 0.5,
        "premium_discount_bias": -0.5, "displacement_bias": 0.5,
        "microstructure_bias": microstructure_bias,
        "orderflow_bias": orderflow_bias,
        "trend_bias": trend_bias,
        "conflict_severity": "NONE",
    }


def make_conf_result(confluence=50, direction_confidence=0.6, conflict=0.2, reversal_risk=20, continuation=50):
    return ConfluenceResult(
        confluence_score=confluence,
        directional_bias=DirectionalBias.LONG,
        directional_confidence=direction_confidence,
        reversal_risk_score=reversal_risk,
        continuation_score=continuation,
        conflict_score=conflict,
    )


class TestRegimeClassifier:
    def test_compute_returns_features(self):
        clf = RegimeClassifier()
        candle = make_candle()
        lsm_data = make_lsm_data(sweeps=2)
        conf = make_conf_result()
        feats = clf.compute(candle, lsm_data, conf)
        assert isinstance(feats, RegimeFeatures)
        assert feats.norm_volatility > 0
        assert feats.volume_ratio == pytest.approx(1.0, rel=0.1)
        assert feats.sweep_intensity == 0.4
        assert feats.trend_strength == 0.5
        assert feats.confluence_score == 50
        assert feats.directional_confidence == 0.6

    def test_volume_ratio_builds_over_window(self):
        clf = RegimeClassifier(window=20)
        for i in range(25):
            vol = 100.0 if i < 15 else 1000.0
            candle = make_candle(volume=vol)
            lsm_data = make_lsm_data(sweeps=0)
            conf = make_conf_result()
            feats = clf.compute(candle, lsm_data, conf)
        assert feats.volume_ratio > 1.0

    def test_reset_clears_state(self):
        clf = RegimeClassifier()
        for _ in range(5):
            clf.compute(make_candle(), make_lsm_data(), make_conf_result())
        clf.reset()
        assert len(clf._ranges) == 0
        assert len(clf._volumes) == 0


class TestReferenceProfile:
    def test_from_features_empty(self):
        profile = ReferenceProfile.from_features([])
        assert profile.num_samples == 0

    def test_from_features_single_set(self):
        clf = RegimeClassifier()
        candle = make_candle()
        feats = clf.compute(candle, make_lsm_data(), make_conf_result())
        profile = ReferenceProfile.from_features([feats])
        assert profile.num_samples == 1
        for f in FEATURE_NAMES:
            assert f in profile.means
            assert f in profile.stds

    def test_from_features_multiple(self):
        features = []
        clf = RegimeClassifier(window=20)
        for i in range(100):
            c = make_candle(close=50000 + i, high=50200 + i, low=49800 + i, volume=100 + i)
            lsm = make_lsm_data(sweeps=i % 3, trend_bias=0.3 + (i % 5) * 0.1)
            conf = make_conf_result(confluence=30 + i % 40)
            feats = clf.compute(c, lsm, conf)
            features.append(feats)
        profile = ReferenceProfile.from_features(features)
        assert profile.num_samples == 100
        assert profile.stds["norm_volatility"] > 0


class TestSimilarityScorer:
    def test_no_reference_returns_100(self):
        scorer = SimilarityScorer()
        feats = RegimeClassifier().compute(make_candle(), make_lsm_data(), make_conf_result())
        assert scorer.score(feats) == 100.0

    def test_identical_features_high_score(self):
        features = []
        clf = RegimeClassifier(window=20)
        for _ in range(50):
            feats = clf.compute(make_candle(), make_lsm_data(), make_conf_result())
            features.append(feats)
        profile = ReferenceProfile.from_features(features)
        scorer = SimilarityScorer(profile)
        score = scorer.score(features[-1])
        assert score >= 80.0

    def test_outlier_features_low_score(self):
        features = []
        clf = RegimeClassifier(window=20)
        for _ in range(100):
            c = make_candle(close=50000, high=50100, low=49900, volume=100)
            lsm = make_lsm_data(sweeps=1, trend_bias=0.3)
            conf = make_conf_result(confluence=50, conflict=0.2)
            feats = clf.compute(c, lsm, conf)
            features.append(feats)
        profile = ReferenceProfile.from_features(features)

        extreme = RegimeFeatures(
            timestamp=datetime(2024, 1, 1),
            norm_volatility=0.1,
            volume_ratio=10.0,
            sweep_intensity=1.0,
            trend_strength=0.0,
            orderflow_strength=0.0,
            microstructure_strength=0.0,
            directional_confidence=0.0,
            conflict_score=0.0,
            confluence_score=0.0,
            structure_event_count=0,
        )
        scorer = SimilarityScorer(profile)
        score = scorer.score(extreme)
        assert score < 50.0


class TestRegimeGate:
    def test_untrained_allows(self):
        gate = RegimeGate()
        dec = gate.check(make_candle(), make_lsm_data(), make_conf_result())
        assert dec.allowed is True
        assert dec.similarity_score == 100.0

    def test_train_then_check_allows(self):
        gate = RegimeGate(RegimeGateConfig(reference_window_candles=0))
        train_candles = [make_candle(timestamp=datetime(2024, 1, 1) + timedelta(minutes=15 * i))
                         for i in range(50)]
        gate.fit(train_candles)
        assert gate.is_trained is True
        dec = gate.check(make_candle(), make_lsm_data(), make_conf_result())
        assert isinstance(dec, RegimeGateDecision)
        assert dec.similarity_score > 0

    def test_resets_state(self):
        gate = RegimeGate()
        gate.fit([make_candle() for _ in range(10)])
        assert gate.is_trained is True
        gate.reset()
        assert gate.is_trained is False

    def test_blocks_extreme_regime(self):
        gate = RegimeGate(RegimeGateConfig(similarity_threshold=50.0, reference_window_candles=0))
        base = datetime(2024, 1, 1)
        train_candles = [make_candle(timestamp=base + timedelta(minutes=15 * j))
                         for j in range(100)]
        gate.fit(train_candles)

        ext_candle = make_candle(high=60000, low=40000, close=50000, volume=10000)
        ext_lsm = make_lsm_data(sweeps=5, trend_bias=1.0, confluence_score=0)
        ext_conf = make_conf_result(confluence=0, direction_confidence=0, conflict=0)
        dec = gate.check(ext_candle, ext_lsm, ext_conf)
        assert dec.allowed is False
        assert "Regime similarity" in dec.rejection_reason
