from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.robustness_lab.replay_runner import ensure_data, run_selective_replay, run_selective_replay_with_governor
from ultimate_trader.drawdown_control import RiskGovernorConfig


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
    test_max_drawdown: float = 0.0
    profitable: bool = False


@dataclass
class GovernorWalkForwardWindow:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    test_trades: int
    test_expectancy: float
    test_profit_factor: float
    test_win_rate: float
    test_avg_trades_per_day: float
    test_max_drawdown: float = 0.0
    profitable: bool = False
    blocked_signals: int = 0


class WalkForwardReplay:
    def __init__(self, frozen_cfg: FrozenConfig):
        self._cfg = frozen_cfg
        self._windows: list[WalkForwardWindow] = []
        self._gov_windows: list[GovernorWalkForwardWindow] = []

    @property
    def windows(self) -> list[WalkForwardWindow]:
        return list(self._windows)

    @property
    def governor_windows(self) -> list[GovernorWalkForwardWindow]:
        return list(self._gov_windows)

    def _warmup_candles(self, timeframe: str) -> int:
        return {"5m": 100, "15m": 50, "30m": 30, "1h": 20}.get(timeframe, 50)

    def run(self, symbol: str = "BTCUSDT", timeframe: str = "15m",
            train_days: int = 30, test_days: int = 15,
            run_governor: bool = False):
        candles = ensure_data(symbol, timeframe, days=365)
        if not candles:
            print(f"  No data for {symbol} {timeframe}")
            return

        warmup = self._warmup_candles(timeframe)
        rcfg = ReplayConfig(
            warmup_candles=warmup, taker_fee_percent=0.04,
            slippage_percent=0.02, funding_per_candle_percent=0.001,
        )
        gov_cfg = RiskGovernorConfig()

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
                test_max_drawdown=test_metrics["max_drawdown"],
                profitable=test_metrics["expectancy"] > 0,
            )
            self._windows.append(w)

            if run_governor:
                gov_metrics, _, _, gov_stats = run_selective_replay_with_governor(
                    test_set, self._cfg, rcfg, gov_cfg,
                )
                gw = GovernorWalkForwardWindow(
                    train_start=train_start.strftime("%Y-%m-%d"),
                    train_end=train_end.strftime("%Y-%m-%d"),
                    test_start=test_start.strftime("%Y-%m-%d"),
                    test_end=test_end.strftime("%Y-%m-%d"),
                    test_trades=gov_metrics["total_trades"],
                    test_expectancy=gov_metrics["expectancy"],
                    test_profit_factor=gov_metrics["profit_factor"],
                    test_win_rate=gov_metrics["win_rate"],
                    test_avg_trades_per_day=gov_metrics["avg_trades_per_day"],
                    test_max_drawdown=gov_metrics["max_drawdown"],
                    profitable=gov_metrics["expectancy"] > 0,
                    blocked_signals=sum(gov_stats.values()),
                )
                self._gov_windows.append(gw)

        self._print_summary(run_governor)

    def _print_summary(self, run_governor: bool):
        if not self._windows:
            print("  No windows formed (insufficient data)")
            return
        self._print_wf_summary("A+ selectivity", self._windows)
        if run_governor and self._gov_windows:
            self._print_wf_summary("A+ + governor", self._gov_windows)

    def _print_wf_summary(self, label: str, windows: list):
        evs = [w.test_expectancy for w in windows]
        profitable = sum(1 for w in windows if w.profitable)
        total = len(windows)
        avg_ev = sum(evs) / len(evs) if evs else 0
        worst = min(evs) if evs else 0
        best = max(evs) if evs else 0
        std = (sum((e - avg_ev) ** 2 for e in evs) / len(evs)) ** 0.5 if len(evs) > 1 else 0
        stability = max(0, 100 - std * 50)
        print(f"  {label} — Windows: {total}, profitable: {profitable}/{total}, "
              f"avg EV: {avg_ev:.2f}R, worst: {worst:.2f}R, best: {best:.2f}R, "
              f"stability: {stability:.0f}%")
