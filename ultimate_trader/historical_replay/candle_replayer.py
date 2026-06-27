from datetime import datetime
from typing import Callable, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle


class CandleReplayer:
    def __init__(self, candles: list[HistoricalCandle], warmup: int = 50) -> None:
        if not candles:
            raise ValueError("No candles provided to CandleReplayer")
        self._all_candles = sorted(candles, key=lambda c: c.timestamp)
        self._warmup = warmup
        self._index = -1
        self._on_candle_handlers: list[Callable[[HistoricalCandle], None]] = []

    def on_candle(self, handler: Callable[[HistoricalCandle], None]) -> None:
        self._on_candle_handlers.append(handler)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def total_candles(self) -> int:
        return len(self._all_candles)

    @property
    def warmup(self) -> int:
        return self._warmup

    @property
    def is_warmup_complete(self) -> bool:
        return self._index >= self._warmup - 1

    def available_candles(self) -> list[HistoricalCandle]:
        if self._index < 0:
            return []
        return self._all_candles[: self._index + 1]

    def current_candle(self) -> Optional[HistoricalCandle]:
        if self._index < 0:
            return None
        return self._all_candles[self._index]

    def rollback(self, steps: int = 1) -> None:
        self._index = max(-1, self._index - steps)

    def step(self) -> Optional[HistoricalCandle]:
        self._index += 1
        if self._index >= len(self._all_candles):
            self._index = len(self._all_candles) - 1
            return None
        candle = self._all_candles[self._index]
        for handler in self._on_candle_handlers:
            handler(candle)
        return candle

    def replay(self) -> None:
        self._index = -1
        while True:
            if self.step() is None:
                break

    def reset(self) -> None:
        self._index = -1

    def get_window(self, lookback: int) -> list[HistoricalCandle]:
        if self._index < 0:
            return []
        start = max(0, self._index + 1 - lookback)
        return self._all_candles[start : self._index + 1]
