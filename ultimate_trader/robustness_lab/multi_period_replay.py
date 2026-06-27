from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.robustness_lab.replay_runner import ensure_data, run_selective_replay


@dataclass
class PeriodResult:
    label: str
    start: str
    end: str
    candles: int
    total_trades: int
    win_rate: float
    expectancy: float
    profit_factor: float
    avg_trades_per_day: float
    max_drawdown: float
    verdict: str = ""


class MultiPeriodReplay:
    def __init__(self, frozen_cfg: FrozenConfig, rcfg: Optional[ReplayConfig] = None):
        self._cfg = frozen_cfg
        self._rcfg = rcfg or ReplayConfig(
            warmup_candles=50, taker_fee_percent=0.04,
            slippage_percent=0.02, funding_per_candle_percent=0.001,
        )
        self._results: list[PeriodResult] = []

    @property
    def results(self) -> list[PeriodResult]:
        return list(self._results)

    def run(self, symbol: str = "BTCUSDT", timeframe: str = "15m"):
        candles = ensure_data(symbol, timeframe, days=120)
        if not candles:
            print(f"  No data for {symbol} {timeframe}")
            return

        now = candles[-1].timestamp
        periods = [
            ("Last 30 days", 0),
            ("Prev 30 days", 30),
            ("Prev 60 days", 60),
            ("Prev 90 days", 90),
        ]

        total_days = (candles[-1].timestamp - candles[0].timestamp).days

        for label, offset_days in periods:
            if offset_days >= total_days:
                print(f"  {label}: insufficient data ({total_days}d available)")
                continue
            if offset_days > 0:
                day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                cutoff_start = day_start - timedelta(days=offset_days)
                cutoff_end = cutoff_start + timedelta(days=30)
                period_candles = [c for c in candles if cutoff_start <= c.timestamp < cutoff_end]
            else:
                cutoff_start = now - timedelta(days=30)
                period_candles = [c for c in candles if c.timestamp >= cutoff_start]

            if len(period_candles) < self._rcfg.warmup_candles + 10:
                print(f"  {label}: too few candles ({len(period_candles)})")
                continue

            metrics, ra, db = run_selective_replay(period_candles, self._cfg, self._rcfg)
            pr = PeriodResult(
                label=label,
                start=period_candles[0].timestamp.strftime("%Y-%m-%d"),
                end=period_candles[-1].timestamp.strftime("%Y-%m-%d"),
                candles=len(period_candles),
                total_trades=metrics["total_trades"],
                win_rate=metrics["win_rate"],
                expectancy=metrics["expectancy"],
                profit_factor=metrics["profit_factor"],
                avg_trades_per_day=metrics["avg_trades_per_day"],
                max_drawdown=metrics["max_drawdown"],
            )
            pr.verdict = self._verdict(pr)
            self._results.append(pr)
            print(f"  {label}: {pr.total_trades}t, WR {pr.win_rate*100:.1f}%, EV {pr.expectancy:.2f}R, PF {pr.profit_factor:.2f}, {pr.avg_trades_per_day:.1f}/d, DD {pr.max_drawdown:.2f}R - {pr.verdict}")

    def _verdict(self, pr: PeriodResult) -> str:
        if pr.total_trades < 5:
            return "INSUFFICIENT_TRADES"
        if pr.expectancy > 0 and pr.profit_factor > 1.2 and pr.avg_trades_per_day <= 4:
            return "EDGE"
        if pr.expectancy > 0:
            return "WEAK_EDGE"
        return "NO_EDGE"
