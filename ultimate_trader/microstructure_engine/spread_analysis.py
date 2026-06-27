from ultimate_trader.microstructure_engine.models import (
    OrderBookSnapshot,
    SpreadState,
)


class SpreadAnalyzer:
    def __init__(
        self,
        wide_bps_threshold: float = 10.0,
        trade_blocking_bps_threshold: float = 50.0,
        unstable_history_count: int = 5,
        unstable_variation_bps: float = 5.0,
    ):
        self.wide_bps_threshold = wide_bps_threshold
        self.trade_blocking_bps_threshold = trade_blocking_bps_threshold
        self.unstable_history_count = unstable_history_count
        self.unstable_variation_bps = unstable_variation_bps
        self._history: list[float] = []

    def analyze(self, snapshot: OrderBookSnapshot) -> SpreadState:
        spread_bps = snapshot.spread_bps
        self._history.append(spread_bps)
        if len(self._history) > self.unstable_history_count * 2:
            self._history.pop(0)

        if spread_bps >= self.trade_blocking_bps_threshold:
            return SpreadState.TRADE_BLOCKING

        if spread_bps >= self.wide_bps_threshold:
            return SpreadState.WIDE

        if self._is_unstable(spread_bps):
            return SpreadState.UNSTABLE

        return SpreadState.NORMAL

    def _is_unstable(self, current_bps: float) -> bool:
        if len(self._history) < self.unstable_history_count:
            return False
        recent = self._history[-self.unstable_history_count:]
        if len(recent) < 2:
            return False
        variations = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        avg_variation = sum(variations) / len(variations)
        return avg_variation > self.unstable_variation_bps

    def reset(self):
        self._history.clear()
