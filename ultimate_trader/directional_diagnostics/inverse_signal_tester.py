from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig, TradeDirection, TradePlan
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator
from ultimate_trader.strategy_engine.engine import StrategyEngine
from ultimate_trader.strategy_engine.models import StrategyConfig


class InverseSignalResult:
    def __init__(self):
        self.label: str = ""
        self.total_trades: int = 0
        self.win_rate: float = 0.0
        self.expectancy: float = 0.0
        self.profit_factor: float = 0.0
        self.max_drawdown: float = 0.0
        self.avg_trades_per_day: float = 0.0

    def __str__(self):
        return f"InverseSignalResult(trades={self.total_trades}, WR={self.win_rate:.1f}%, EV={self.expectancy:.2f}R)"


class InverseSignalTestResults:
    def __init__(self):
        self.original: InverseSignalResult = InverseSignalResult()
        self.inverted: InverseSignalResult = InverseSignalResult()
        self.weak_blocked: InverseSignalResult = InverseSignalResult()

    @property
    def original_trades(self):
        return self.original.total_trades

    @property
    def inverted_trades(self):
        return self.inverted.total_trades

    @property
    def weak_blocked_trades(self):
        return self.weak_blocked.total_trades

    @property
    def original_stats(self):
        return {"total_trades": self.original.total_trades, "win_rate": self.original.win_rate, "expectancy": self.original.expectancy, "profit_factor": self.original.profit_factor, "avg_trades_per_day": self.original.avg_trades_per_day}

    @property
    def inverted_stats(self):
        return {"total_trades": self.inverted.total_trades, "win_rate": self.inverted.win_rate, "expectancy": self.inverted.expectancy, "profit_factor": self.inverted.profit_factor, "avg_trades_per_day": self.inverted.avg_trades_per_day}

    @property
    def weak_blocked_stats(self):
        return {"total_trades": self.weak_blocked.total_trades, "win_rate": self.weak_blocked.win_rate, "expectancy": self.weak_blocked.expectancy, "profit_factor": self.weak_blocked.profit_factor, "avg_trades_per_day": self.weak_blocked.avg_trades_per_day}


class InverseSignalTester:
    def __init__(self, weak_confidence_threshold: float = 70.0):
        self.weak_confidence_threshold = weak_confidence_threshold

    def test_variants(
        self,
        candles: list[HistoricalCandle],
        lsm_data_provider: Any,
        strategy_config: StrategyConfig,
        replay_config: ReplayConfig,
    ) -> InverseSignalTestResults:
        results = InverseSignalTestResults()
        results.original = self._run_replay(candles, lsm_data_provider, strategy_config, replay_config, invert=False)
        results.inverted = self._run_replay(candles, lsm_data_provider, strategy_config, replay_config, invert=True)
        results.weak_blocked = self._run_replay(candles, lsm_data_provider, strategy_config, replay_config, block_weak=True)
        return results

    def test_variant(self, trades: list[dict], mode: str) -> dict:
        """Analyze a list of trade dicts in original/inverted/weak_blocked mode.

        Each trade dict: {"direction": str, "net_r": float, "confidence": float}
        """
        if mode == "original":
            filtered = trades
        elif mode == "inverted":
            filtered = []
            for t in trades:
                inv_t = dict(t)
                inv_t["direction"] = "SHORT" if t.get("direction", "LONG") == "LONG" else "LONG"
                inv_t["net_r"] = -t.get("net_r", 0)
                filtered.append(inv_t)
        elif mode == "weak_blocked":
            filtered = [t for t in trades if t.get("confidence", 0) >= self.weak_confidence_threshold]
        else:
            filtered = trades

        total = len(filtered)
        if total == 0:
            return {"total_trades": 0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "avg_trades_per_day": 0.0, "direction": ""}

        wins = sum(1 for t in filtered if t.get("net_r", 0) > 0)
        win_rate = (wins / total) * 100
        expectancy = sum(t.get("net_r", 0) for t in filtered) / total

        gross_profit = sum(t.get("net_r", 0) for t in filtered if t.get("net_r", 0) > 0)
        gross_loss = abs(sum(t.get("net_r", 0) for t in filtered if t.get("net_r", 0) < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        first_dir = filtered[0].get("direction", "") if filtered else ""

        return {
            "total_trades": total,
            "win_rate": win_rate,
            "expectancy": expectancy,
            "profit_factor": pf,
            "avg_trades_per_day": total / 30.0 if total > 0 else 0.0,
            "direction": first_dir,
        }

    def test_variants_simple(self, trades: list[dict]) -> "InverseSignalTestResults":
        results = InverseSignalTestResults()

        def _fill(r, stats):
            r.total_trades = stats["total_trades"]
            r.win_rate = stats["win_rate"]
            r.expectancy = stats["expectancy"]
            r.profit_factor = stats["profit_factor"]
            r.avg_trades_per_day = stats["avg_trades_per_day"]

        _fill(results.original, self.test_variant(trades, "original"))
        _fill(results.inverted, self.test_variant(trades, "inverted"))
        _fill(results.weak_blocked, self.test_variant(trades, "weak_blocked"))
        return results

    def _run_replay(
        self,
        candles: list[HistoricalCandle],
        lsm_data_provider: Any,
        strategy_config: StrategyConfig,
        replay_config: ReplayConfig,
        invert: bool = False,
        block_weak: bool = False,
    ) -> InverseSignalResult:
        warmup = replay_config.warmup_candles
        sim = TradeSimulator(replay_config)
        engine = StrategyEngine(strategy_config)
        daily_counts: dict[str, int] = defaultdict(int)
        day_wins: dict[str, int] = defaultdict(int)
        day_losses: dict[str, int] = defaultdict(int)

        for i, candle in enumerate(candles):
            engine.add_candle(candle)
            if i < warmup:
                continue

            lsm_data: dict = {}
            if lsm_data_provider:
                try:
                    lsm_data = lsm_data_provider(candle, i)
                except Exception:
                    pass

            direction = lsm_data.get("direction", "LONG")
            if invert:
                direction = "SHORT" if direction == "LONG" else "LONG"

            entry_price = candle.close
            stop_loss_price = candle.close - (candle.high - candle.low) * 1.5
            target_price = candle.close + (candle.high - candle.low) * 1.5 * 3.0
            if direction == "SHORT":
                stop_loss_price = candle.close + (candle.high - candle.low) * 1.5
                target_price = candle.close - (candle.high - candle.low) * 1.5 * 3.0

            if block_weak:
                conf = lsm_data.get("confluence_score", 0)
                minimum = 50.0
                if daily_counts[candle.timestamp.strftime("%Y-%m-%d")] >= 4:
                    minimum = 70.0
                if conf < minimum:
                    plan = None
                else:
                    td = TradeDirection.LONG if direction == "LONG" else TradeDirection.SHORT
                    candidate = engine.evaluate(candle=candle, lsm_data=lsm_data,
                                                direction=td, entry_price=entry_price,
                                                stop_loss=stop_loss_price, target_price=target_price)
                    plan = TradePlan(
                        plan_id=f"WS-{i}", symbol=candle.symbol, direction=td,
                        signal_time=candle.timestamp,
                        entry_zone_high=entry_price + (candle.high - candle.low) * 0.1,
                        entry_zone_low=entry_price - (candle.high - candle.low) * 0.1,
                        stop_loss=stop_loss_price, target_price=target_price,
                        plan_reason="weak-blocked",
                    ) if candidate else None
            else:
                td = TradeDirection.LONG if direction == "LONG" else TradeDirection.SHORT
                candidate = engine.evaluate(candle=candle, lsm_data=lsm_data,
                                            direction=td, entry_price=entry_price,
                                            stop_loss=stop_loss_price, target_price=target_price)
                plan = TradePlan(
                    plan_id=f"TS-{i}", symbol=candle.symbol, direction=td,
                    signal_time=candle.timestamp,
                    entry_zone_high=entry_price + (candle.high - candle.low) * 0.1,
                    entry_zone_low=entry_price - (candle.high - candle.low) * 0.1,
                    stop_loss=stop_loss_price, target_price=target_price,
                    plan_reason="test",
                ) if candidate else None

            from ultimate_trader.liquidity_smart_money.models import Candle as LsmCandle
            lc = LsmCandle(symbol=candle.symbol, timeframe=candle.timeframe,
                           timestamp=candle.timestamp, open=candle.open,
                           high=candle.high, low=candle.low, close=candle.close,
                           volume=candle.volume)
            trades = sim.process_candle(lc, [plan] if plan else [])
            for t in trades:
                day_key = candle.timestamp.strftime("%Y-%m-%d")
                daily_counts[day_key] += 1
                if t.net_r > 0:
                    day_wins[day_key] += 1
                else:
                    day_losses[day_key] += 1

        result = InverseSignalResult()
        completed = sim.completed_trades
        result.total_trades = len(completed)
        if completed:
            wins = sum(1 for t in completed if t.net_r > 0)
            result.win_rate = (wins / len(completed)) * 100
            result.expectancy = sum(t.net_r for t in completed) / len(completed)
            gross_profit = sum(t.net_r for t in completed if t.net_r > 0)
            gross_loss = abs(sum(t.net_r for t in completed if t.net_r < 0))
            result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        days_traded = len(daily_counts)
        result.avg_trades_per_day = result.total_trades / days_traded if days_traded > 0 else 0.0

        return result
