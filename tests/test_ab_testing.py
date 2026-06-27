from datetime import datetime

import pytest

from ultimate_trader.validation_lab.ab_testing import ABTestingEngine
from ultimate_trader.validation_lab.performance_metrics import (
    Direction,
    TradeResult,
)


def make_trades(net_rs: list[float]) -> list[TradeResult]:
    return [
        TradeResult(
            trade_id=f"T{i}",
            hypothesis_id="RH-TEST",
            symbol="BTCUSDT",
            entry_time=datetime(2024, 1, 1),
            direction=Direction.LONG,
            entry_price=100.0,
            gross_r=r,
            net_r=r,
        )
        for i, r in enumerate(net_rs)
    ]


class TestABTestingEngine:
    def test_identifies_winner(self):
        engine = ABTestingEngine()
        trades_a = make_trades([2.0, 1.5, 1.0, 0.5, 1.0] * 10)
        trades_b = make_trades([0.1, -0.2, 0.3, -0.1, 0.0] * 10)
        result = engine.compare(trades_a, trades_b, "A", "B")
        assert result.winner == "A"

    def test_prefers_simpler_model_when_similar(self):
        engine = ABTestingEngine()
        trades_a = make_trades([1.0, 0.9, 1.1, 0.8, 1.0] * 8)
        trades_b = make_trades([1.0, 1.0, 1.0, 1.0, 1.0] * 10)
        result = engine.compare(trades_a, trades_b, "Complex", "Simple")
        if result.winner:
            assert result.simpler_model_preferred

    def test_performance_difference_included(self):
        engine = ABTestingEngine()
        trades_a = make_trades([2.0] * 10)
        trades_b = make_trades([1.0] * 10)
        result = engine.compare(trades_a, trades_b)
        assert "expectancy_r_diff" in result.performance_difference

    def test_conclusion_present(self):
        engine = ABTestingEngine()
        trades_a = make_trades([1.0] * 10)
        trades_b = make_trades([0.5] * 10)
        result = engine.compare(trades_a, trades_b)
        assert len(result.conclusion) > 0
