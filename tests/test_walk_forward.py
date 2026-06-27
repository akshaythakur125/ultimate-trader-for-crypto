from datetime import datetime

import pytest

from ultimate_trader.validation_lab.performance_metrics import (
    Direction,
    ExitReason,
    TradeResult,
)
from ultimate_trader.validation_lab.walk_forward import WalkForwardValidator


def make_trades(net_rs: list[float]) -> list[TradeResult]:
    trades = []
    for i, r in enumerate(net_rs):
        trades.append(TradeResult(
            trade_id=f"T{i}",
            hypothesis_id="RH-TEST",
            symbol="BTCUSDT",
            entry_time=datetime(2024, 1, 1),
            direction=Direction.LONG,
            entry_price=100.0,
            gross_r=r,
            net_r=r,
        ))
    return trades


class TestWalkForwardValidator:
    def test_consistent_performance_passes(self):
        validator = WalkForwardValidator()
        pos_trades = make_trades([1.0, 2.0, 0.5, 1.5, 1.0] * 10)
        window_a = pos_trades[:20]
        window_b = pos_trades[20:40]
        result = validator.evaluate([window_a, window_b])
        assert result.passed

    def test_insufficient_windows_fails(self):
        validator = WalkForwardValidator()
        result = validator.evaluate([make_trades([1.0])])
        assert not result.passed

    def test_performance_decay_detected(self):
        validator = WalkForwardValidator()
        good = make_trades([2.0, 1.5, 1.0] * 7)
        bad = make_trades([-0.5, -1.0, 0.2] * 7)
        result = validator.evaluate([good, bad])
        assert result.performance_decay_detected

    def test_consistency_score(self):
        validator = WalkForwardValidator()
        pos = make_trades([1.0] * 15)
        neg = make_trades([-0.5] * 15)
        result = validator.evaluate([pos, pos, neg])
        assert 0 <= result.consistency_score <= 1.0
