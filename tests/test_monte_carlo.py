from datetime import datetime

import pytest

from ultimate_trader.validation_lab.monte_carlo import MonteCarloSimulator
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


class TestMonteCarloSimulator:
    def test_simulates_on_sample_trades(self):
        simulator = MonteCarloSimulator()
        trades = make_trades([1.0, -0.5, 2.0, -0.3, 1.5, -0.7, 1.0, 0.5] * 10)
        result = simulator.simulate(trades, num_simulations=100)
        assert result.simulations_run == 100
        assert result.median_return_r != 0.0

    def test_insufficient_trades_fails(self):
        simulator = MonteCarloSimulator()
        trades = make_trades([1.0, 2.0, 3.0])
        result = simulator.simulate(trades)
        assert not result.passed

    def test_probability_of_ruin(self):
        simulator = MonteCarloSimulator()
        trades = make_trades([-1.0] * 5 + [0.1] * 95)
        result = simulator.simulate(trades, num_simulations=100)
        assert 0 <= result.probability_of_ruin <= 1.0

    def test_confidence_interval(self):
        simulator = MonteCarloSimulator()
        trades = make_trades([1.0, -0.5, 2.0, -0.3, 1.5] * 20)
        result = simulator.simulate(trades, num_simulations=100)
        assert result.confidence_interval_low <= result.confidence_interval_high
