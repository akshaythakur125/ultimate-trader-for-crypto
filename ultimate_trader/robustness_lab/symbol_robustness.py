from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.robustness_lab.replay_runner import ensure_data, run_selective_replay


@dataclass
class SymbolResult:
    symbol: str
    timeframe: str
    candles: int
    total_trades: int
    win_rate: float
    expectancy: float
    profit_factor: float
    avg_trades_per_day: float
    max_drawdown: float
    data_available: bool = True
    error: str = ""


class SymbolRobustness:
    def __init__(self, frozen_cfg: FrozenConfig, rcfg: Optional[ReplayConfig] = None):
        self._cfg = frozen_cfg
        self._rcfg = rcfg or ReplayConfig(
            warmup_candles=50, taker_fee_percent=0.04,
            slippage_percent=0.02, funding_per_candle_percent=0.001,
        )
        self._results: list[SymbolResult] = []

    @property
    def results(self) -> list[SymbolResult]:
        return list(self._results)

    def run(self, symbols: Optional[list[str]] = None, timeframe: str = "15m"):
        targets = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        for symbol in targets:
            candles = ensure_data(symbol, timeframe, days=90)
            if len(candles) < self._rcfg.warmup_candles + 10:
                err_msg = "No data" if not candles else f"Only {len(candles)} candles"
                self._results.append(SymbolResult(
                    symbol=symbol, timeframe=timeframe,
                    candles=len(candles), total_trades=0,
                    win_rate=0, expectancy=0, profit_factor=0,
                    avg_trades_per_day=0, max_drawdown=0,
                    data_available=False, error=err_msg,
                ))
                print(f"  {symbol} {timeframe}: DATA NOT AVAILABLE ({err_msg})")
                continue

            metrics, ra, db = run_selective_replay(candles, self._cfg, self._rcfg)
            sr = SymbolResult(
                symbol=symbol, timeframe=timeframe,
                candles=len(candles),
                total_trades=metrics["total_trades"],
                win_rate=metrics["win_rate"],
                expectancy=metrics["expectancy"],
                profit_factor=metrics["profit_factor"],
                avg_trades_per_day=metrics["avg_trades_per_day"],
                max_drawdown=metrics["max_drawdown"],
            )
            self._results.append(sr)
            print(f"  {symbol} {timeframe}: {sr.total_trades}t, WR {sr.win_rate*100:.1f}%, EV {sr.expectancy:.2f}R, PF {sr.profit_factor:.2f}, {sr.avg_trades_per_day:.1f}/d")
