import uuid
from datetime import datetime
from typing import Any, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig, TradeDirection, TradePlan
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator
from ultimate_trader.strategy_engine.filters import ALL_FILTERS
from ultimate_trader.strategy_engine.models import (
    FilterResult,
    StrategyCandidate,
    StrategyConfig,
    StrategyContext,
)
from ultimate_trader.strategy_engine.scorer import ConfidenceScorer


class StrategyEngine:
    def __init__(self, config: Optional[StrategyConfig] = None) -> None:
        self._config = config or StrategyConfig()
        self._scorer = ConfidenceScorer()
        self._candidates: list[StrategyCandidate] = []
        self._candles_history: list[HistoricalCandle] = []

    @property
    def config(self) -> StrategyConfig:
        return self._config

    @property
    def candidates(self) -> list[StrategyCandidate]:
        return list(self._candidates)

    @property
    def candles_history(self) -> list[HistoricalCandle]:
        return list(self._candles_history)

    def add_candle(self, candle: HistoricalCandle) -> None:
        self._candles_history.append(candle)

    def evaluate(
        self,
        candle: HistoricalCandle,
        lsm_data: Optional[dict[str, Any]] = None,
        direction: TradeDirection = TradeDirection.LONG,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        target_price: float = 0.0,
    ) -> Optional[StrategyCandidate]:
        if not self._candles_history:
            self._candles_history.append(candle)

        ctx = StrategyContext(
            candle=candle,
            candles_history=self._candles_history,
            direction=direction,
            entry_price=entry_price or candle.close,
            stop_loss=stop_loss,
            target_price=target_price,
        )

        if lsm_data:
            ctx.confluence_score = lsm_data.get("confluence_score", 0.0)
            ctx.trade_permission = lsm_data.get("trade_permission", "ALLOW")
            ctx.lsm_swing_highs = lsm_data.get("swing_highs", [])
            ctx.lsm_swing_lows = lsm_data.get("swing_lows", [])
            ctx.lsm_sweeps = lsm_data.get("sweeps", [])
            ctx.lsm_structure_events = lsm_data.get("structure_events", [])
            ctx.lsm_fvgs = lsm_data.get("fvgs", [])
            ctx.lsm_order_blocks = lsm_data.get("order_blocks", [])
            ctx.risk_score = lsm_data.get("risk_score", 0.0)

        filter_results, total_confidence = self._scorer.score(ctx, self._config)

        filters_passed = [name for name, r in filter_results.items() if r.passed and r.data_available]
        filters_failed = [name for name, r in filter_results.items() if not r.passed and r.data_available]
        filters_unavailable = [name for name, r in filter_results.items() if not r.data_available]

        approved = total_confidence >= self._config.confidence_threshold
        rejection_reason = ""
        if not approved:
            if filters_failed:
                top_failures = filters_failed[:3]
                rejection_reason = f"Confidence {total_confidence:.1f} < {self._config.confidence_threshold}. Failed: {', '.join(top_failures)}"
            elif filters_unavailable:
                rejection_reason = f"Confidence {total_confidence:.1f} < {self._config.confidence_threshold}. Insufficient data from {len(filters_unavailable)} filters"
            else:
                rejection_reason = f"Confidence {total_confidence:.1f} < {self._config.confidence_threshold}"

        directional_components: dict[str, float] = {}
        directional_vote = direction.value if direction else ""
        conflict_severity = "NONE"
        if lsm_data:
            for key in ("sweep_bias", "structure_bias", "fvg_bias", "order_block_bias",
                        "premium_discount_bias", "displacement_bias", "microstructure_bias",
                        "orderflow_bias", "trend_bias"):
                val = lsm_data.get(key)
                if val is not None:
                    directional_components[key] = val
            directional_components["confluence_score"] = lsm_data.get("confluence_score", 0.0)
            conflict_severity = lsm_data.get("conflict_severity", "NONE")

        candidate = StrategyCandidate(
            candidate_id=f"SC-{uuid.uuid4().hex[:8].upper()}",
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            timestamp=candle.timestamp,
            direction=direction,
            entry_price=entry_price or candle.close,
            stop_loss=stop_loss,
            target_price=target_price,
            total_confidence=total_confidence,
            filter_results=filter_results,
            approved=approved,
            rejection_reason=rejection_reason,
            filters_passed=filters_passed,
            filters_failed=filters_failed,
            filters_unavailable=filters_unavailable,
            directional_components=directional_components,
            directional_vote=directional_vote,
            conflict_severity=conflict_severity,
        )

        self._candidates.append(candidate)
        return candidate if approved else None

    def reset(self) -> None:
        self._candidates.clear()
        self._candles_history.clear()


def run_strategy_replay(
    candles: list[HistoricalCandle],
    lsm_data_provider: Any,
    config: Optional[StrategyConfig] = None,
    replay_config: Optional[ReplayConfig] = None,
) -> tuple[list[Any], list[Any], Any]:
    strategy_config = config or StrategyConfig()
    rcfg = replay_config or ReplayConfig(
        taker_fee_percent=0.04, slippage_percent=0.02,
        funding_per_candle_percent=0.001,
        warmup_candles=50,
    )

    engine = StrategyEngine(strategy_config)
    sim = TradeSimulator(rcfg)
    warmup = rcfg.warmup_candles
    all_trades: list = []

    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < warmup:
            continue

        lsm_data = {}
        if lsm_data_provider:
            try:
                lsm_data = lsm_data_provider(candle, i)
            except Exception:
                pass

        direction = TradeDirection.LONG
        entry_price = candle.close
        stop_loss_price = candle.close - (candle.high - candle.low) * 1.5
        target_price = candle.close + (candle.high - candle.low) * 1.5 * 3.0

        if lsm_data.get("direction") == "SHORT":
            direction = TradeDirection.SHORT
            stop_loss_price = candle.close + (candle.high - candle.low) * 1.5
            target_price = candle.close - (candle.high - candle.low) * 1.5 * 3.0

        plan = None
        candidate = engine.evaluate(
            candle=candle,
            lsm_data=lsm_data,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss_price,
            target_price=target_price,
        )

        if candidate is not None:
            plan = TradePlan(
                plan_id=f"SP-{uuid.uuid4().hex[:8].upper()}",
                symbol=candle.symbol,
                direction=direction,
                signal_time=candle.timestamp,
                entry_zone_high=entry_price + (candle.high - candle.low) * 0.1,
                entry_zone_low=entry_price - (candle.high - candle.low) * 0.1,
                stop_loss=stop_loss_price,
                target_price=target_price,
                plan_reason=f"Strategy confidence={candidate.total_confidence:.1f}",
            )

        from ultimate_trader.liquidity_smart_money.models import Candle as LsmCandle
        lc = LsmCandle(
            symbol=candle.symbol, timeframe=candle.timeframe,
            timestamp=candle.timestamp, open=candle.open,
            high=candle.high, low=candle.low, close=candle.close,
            volume=candle.volume,
        )
        plans = [plan] if plan else []
        results = sim.process_candle(lc, plans)
        all_trades.extend(results)

    return engine.candidates, sim.completed_trades, sim
