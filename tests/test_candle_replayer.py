from datetime import datetime

import pytest

from ultimate_trader.historical_replay.candle_replayer import CandleReplayer
from ultimate_trader.historical_replay.models import HistoricalCandle


def make_candle(ts: datetime, close: float) -> HistoricalCandle:
    return HistoricalCandle(
        symbol="BTCUSDT", timeframe="1h", timestamp=ts,
        open=close, high=close + 1, low=close - 1, close=close, volume=100.0,
    )


class TestCandleReplayer:
    def test_rejects_empty_candles(self):
        with pytest.raises(ValueError):
            CandleReplayer([])

    def test_no_candles_available_before_first_step(self):
        candles = [make_candle(datetime(2024, 1, 1, i), 100.0 + i) for i in range(10)]
        r = CandleReplayer(candles, warmup=3)
        assert r.available_candles() == []
        assert r.current_candle() is None
        assert r.current_index == -1

    def test_step_returns_candle_and_tracks_index(self):
        candles = [make_candle(datetime(2024, 1, 1, i), 100.0 + i) for i in range(10)]
        r = CandleReplayer(candles, warmup=3)
        c = r.step()
        assert c is not None
        assert c.close == 100.0
        assert r.current_index == 0
        assert r.available_candles() == [c]

    def test_replay_empty_after_last_candle(self):
        candles = [make_candle(datetime(2024, 1, 1, 0), 100.0)]
        r = CandleReplayer(candles, warmup=1)
        assert r.step() is not None
        assert r.step() is None

    def test_warmup_tracking(self):
        candles = [make_candle(datetime(2024, 1, 1, i), 100.0 + i) for i in range(10)]
        r = CandleReplayer(candles, warmup=5)
        assert r.is_warmup_complete is False
        for _ in range(4):
            r.step()
        assert r.is_warmup_complete is False
        r.step()
        assert r.is_warmup_complete is True

    def test_no_future_data_leakage(self):
        candles = [make_candle(datetime(2024, 1, 1, i), 100.0 + i) for i in range(10)]
        r = CandleReplayer(candles, warmup=3)
        for _ in range(5):
            r.step()
        available = r.available_candles()
        assert len(available) == 5
        for c in available:
            assert c.timestamp <= candles[4].timestamp

    def test_rolling_window(self):
        candles = [make_candle(datetime(2024, 1, 1, i), 100.0 + i) for i in range(10)]
        r = CandleReplayer(candles, warmup=3)
        for _ in range(8):
            r.step()
        window = r.get_window(3)
        assert len(window) == 3
        assert window[-1].close == 107.0

    def test_reset_restores_state(self):
        candles = [make_candle(datetime(2024, 1, 1, i), 100.0 + i) for i in range(10)]
        r = CandleReplayer(candles, warmup=3)
        for _ in range(5):
            r.step()
        assert r.current_index == 4
        r.reset()
        assert r.current_index == -1
        assert r.current_candle() is None

    def test_on_candle_handler_called(self):
        candles = [make_candle(datetime(2024, 1, 1, 0), 100.0)]
        r = CandleReplayer(candles, warmup=1)
        results = []
        r.on_candle(lambda c: results.append(c.close))
        r.step()
        assert results == [100.0]

    def test_rollback(self):
        candles = [make_candle(datetime(2024, 1, 1, i), 100.0 + i) for i in range(5)]
        r = CandleReplayer(candles, warmup=1)
        r.step()
        assert r.current_index == 0
        r.rollback(1)
        assert r.current_index == -1
        r.rollback(1)
        assert r.current_index == -1
