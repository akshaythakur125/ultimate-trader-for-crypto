from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.robustness_lab.replay_runner import ensure_data, run_selective_replay


@dataclass
class WalkForwardWindow:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_trades: int
    test_trades: int
    test_expectancy: float
    test_profit_factor: float
    test_win_rate: float
    test_avg_trades_per_day: float
    profitable: bool = False


class WalkForwardReplay:
    def __init__(self, frozen_cfg: FrozenConfig):
        self._cfg = frozen_cfg
        self._windows: list[WalkForwardWindow] = []

    @property
    def windows(self) -> list[WalkForwardWindow]:
        return list(self._windows)

    def run(self, symbol: str = "BTCUSDT", timeframe: str = "15m", train_days: int = 30, test_days: int = 15):
        candles = ensure_data(symbol, timeframe, days=120)
        if not candles:
            print(f"  No data for {symbol} {timeframe}")
            return

        warmup = 50
        rcfg = ReplayConfig(
            warmup_candles=warmup, taker_fee_percent=0.04,
            slippage_percent=0.02, funding_per_candle_percent=0.001,
        )

        total_days = (candles[-1].timestamp - candles[0].timestamp).days
        step = test_days

        for offset in range(0, total_days - train_days - test_days, step):
            end_ts = candles[-1].timestamp
            ref = end_ts - timedelta(days=offset)
            train_end = ref
            train_start = ref - timedelta(days=train_days)
            test_end = ref + timedelta(days=test_days) if offset > 0 else end_ts
            test_start = ref

            train_set = [c for c in candles if train_start <= c.timestamp < train_end]
            test_set = [c for c in candles if test_start <= c.timestamp < test_end]

            if len(train_set) < warmup + 10 or len(test_set) < 10:
                continue

            train_metrics, _, _ = run_selective_replay(train_set, self._cfg, rcfg)
            test_metrics, _, _ = run_selective_replay(test_set, self._cfg, rcfg)

            w = WalkForwardWindow(
                train_start=train_start.strftime("%Y-%m-%d"),
                train_end=train_end.strftime("%Y-%m-%d"),
                test_start=test_start.strftime("%Y-%m-%d"),
                test_end=test_end.strftime("%Y-%m-%d"),
                train_trades=train_metrics["total_trades"],
                test_trades=test_metrics["total_trades"],
                test_expectancy=test_metrics["expectancy"],
                test_profit_factor=test_metrics["profit_factor"],
                test_win_rate=test_metrics["win_rate"],
                test_avg_trades_per_day=test_metrics["avg_trades_per_day"],
                profitable=test_metrics["expectancy"] > 0,
            )
            self._windows.append(w)

        if self._windows:
            evs = [w.test_expectancy for w in self._windows]
            avg_ev = sum(evs) / len(evs)
            profitable = sum(1 for w in self._windows if w.profitable)
            total = len(self._windows)
            worst = min(evs)
            best = max(evs)
            std = (sum((e - avg_ev) ** 2 for e in evs) / len(evs)) ** 0.5
            stability = max(0, 100 - std * 50)
            print(f"  Windows: {total}, profitable: {profitable}/{total}, avg EV: {avg_ev:.2f}R, worst: {worst:.2f}R, best: {best:.2f}R, stability: {stability:.0f}%")
        else:
            print("  No windows formed (insufficient data)")
