import pytest
from datetime import datetime
from ultimate_trader.directional_diagnostics.direction_conflict_detector import (
    DirectionConflictDetector,
    DirectionConflictResult,
)


class TestDirectionConflictDetector:
    def test_no_conflict_all_long(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="LONG",
            microstructure_bias="BULLISH",
            orderflow_bias="LONG",
            strategy_bias="LONG",
        )
        assert not result.has_conflict
        assert result.recommended_action == "ALLOW"

    def test_no_conflict_all_short(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="SHORT",
            microstructure_bias="BEARISH",
            orderflow_bias="SHORT",
            strategy_bias="SHORT",
        )
        assert not result.has_conflict
        assert result.recommended_action == "ALLOW"

    def test_direct_conflict_50_50(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="LONG",
            microstructure_bias="LONG",
            orderflow_bias="SHORT",
            strategy_bias="SHORT",
        )
        assert result.has_conflict
        assert result.severity == "HIGH"
        assert result.recommended_action == "BLOCK"

    def test_moderate_conflict(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="LONG",
            microstructure_bias="LONG",
            orderflow_bias="LONG",
            strategy_bias="SHORT",
        )
        assert result.has_conflict
        assert result.severity == "MODERATE"
        assert result.recommended_action == "HUMAN_REVIEW"

    def test_no_data_available(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="",
            microstructure_bias="",
            orderflow_bias="",
            strategy_bias="",
        )
        assert not result.has_conflict
        assert result.recommended_action == "HUMAN_REVIEW"

    def test_orderflow_microstructure_conflict(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="LONG",
            microstructure_bias="BEARISH",
            orderflow_bias="LONG",
            strategy_bias="LONG",
        )
        assert result.has_conflict
        assert result.severity == "HIGH"

    def test_reverse_orderflow_microstructure_conflict(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="SHORT",
            microstructure_bias="BULLISH",
            orderflow_bias="SHORT",
            strategy_bias="SHORT",
        )
        assert result.has_conflict
        assert result.severity == "HIGH"

    def test_all_neutral(self):
        detector = DirectionConflictDetector()
        result = detector.detect(
            lsm_bias="NEUTRAL",
            microstructure_bias="BALANCED",
            orderflow_bias="NEUTRAL",
            strategy_bias="NEUTRAL",
        )
        assert not result.has_conflict
