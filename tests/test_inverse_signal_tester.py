import pytest
from datetime import datetime
from ultimate_trader.directional_diagnostics.inverse_signal_tester import InverseSignalTester, InverseSignalResult


class TestInverseSignalTester:
    def test_empty_trades(self):
        tester = InverseSignalTester()
        result = tester.test_variants_simple([])
        assert result.original_trades == 0
        assert result.inverted_trades == 0
        assert result.weak_blocked_trades == 0

    def test_original_unchanged(self):
        tester = InverseSignalTester()
        trades = [
            {"direction": "LONG", "net_r": 2.0, "confidence": 80.0},
            {"direction": "SHORT", "net_r": -1.0, "confidence": 70.0},
        ]
        result = tester.test_variants_simple(trades)
        assert result.original_trades == 2
        assert result.inverted_trades == 2
        assert result.weak_blocked_trades >= 0

    def test_inverted_reverses_net_r(self):
        tester = InverseSignalTester()
        trades = [{"direction": "LONG", "net_r": 2.0, "confidence": 80.0}]
        result = tester.test_variants_simple(trades)
        assert result.inverted_trades == 1
        assert result.inverted_stats.get("expectancy", 0) == -2.0

    def test_weak_blocked_reduces_trades(self):
        tester = InverseSignalTester(weak_confidence_threshold=85.0)
        trades = [
            {"direction": "LONG", "net_r": 1.0, "confidence": 70.0},
            {"direction": "SHORT", "net_r": 2.0, "confidence": 90.0},
        ]
        result = tester.test_variants_simple(trades)
        assert result.weak_blocked_trades == 1

    def test_test_variant_original(self):
        tester = InverseSignalTester()
        trades = [{"direction": "LONG", "net_r": 2.0, "confidence": 80.0}]
        result = tester.test_variant(trades, "original")
        assert result["total_trades"] == 1
        assert result["win_rate"] == 100.0

    def test_test_variant_inverted(self):
        tester = InverseSignalTester()
        trades = [{"direction": "LONG", "net_r": 2.0, "confidence": 80.0}]
        result = tester.test_variant(trades, "inverted")
        assert result["total_trades"] == 1
        assert result["direction"] == "SHORT"

    def test_test_variant_weak_blocked(self):
        tester = InverseSignalTester(weak_confidence_threshold=70.0)
        trades = [
            {"direction": "LONG", "net_r": 2.0, "confidence": 65.0},
            {"direction": "LONG", "net_r": 2.0, "confidence": 80.0},
        ]
        result = tester.test_variant(trades, "weak_blocked")
        assert result["total_trades"] == 1

    def test_result_string_representation(self):
        r = InverseSignalResult()
        r.total_trades = 5
        r.win_rate = 60.0
        r.expectancy = 0.5
        s = str(r)
        assert "InverseSignalResult" in s
