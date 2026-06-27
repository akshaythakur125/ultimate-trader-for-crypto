#!/usr/bin/env python3
"""Phase 3 Prompt 5: A+ Selectivity Gate + Real Pipeline Replay.

Usage:
    python scripts/run_selective_replay.py
"""

import csv
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig, TradeDirection, TradePlan
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator
from ultimate_trader.liquidity_smart_money import (
    Candle as LsmCandle,
    ConfluenceEngine,
    DirectionalBias,
    DisplacementEngine,
    FairValueGapDetector,
    LiquidityPoolDetector,
    MarketStructureEngine,
    OrderBlockDetector,
    PremiumDiscountEngine,
    SweepDetector,
    SwingDetector,
)
from ultimate_trader.selectivity_engine import (
    CandidateRanker,
    DailySelector,
    DailySelectorConfig,
    QualityGate,
    QualityGateConfig,
    RejectionReasonAnalyzer,
    SelectivityReport,
)
from ultimate_trader.strategy_engine.engine import StrategyEngine
from ultimate_trader.strategy_engine.models import StrategyConfig

HISTORICAL_DATA = os.path.join("data", "historical", "BTCUSDT_15m.csv")


def load_candles(path: str) -> list[HistoricalCandle]:
    candles = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                candles.append(HistoricalCandle(
                    symbol=row.get("symbol", "BTCUSDT"),
                    timeframe=row.get("timeframe", "15m"),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                ))
            except (KeyError, ValueError):
                continue
    return candles


def hc_to_lsm(hc: HistoricalCandle) -> LsmCandle:
    return LsmCandle(
        symbol=hc.symbol, timeframe=hc.timeframe,
        timestamp=hc.timestamp, open=hc.open,
        high=hc.high, low=hc.low, close=hc.close,
        volume=hc.volume,
    )


class RealTimeLsmPipeline:
    """Produces lsm_data + ConfluenceResult per candle using all LSM detectors."""

    def __init__(self):
        self._sd = SwingDetector()
        self._ld = LiquidityPoolDetector()
        self._swd = SweepDetector()
        self._ms = MarketStructureEngine()
        self._fvg = FairValueGapDetector()
        self._ob = OrderBlockDetector()
        self._pd = PremiumDiscountEngine()
        self._disp = DisplacementEngine()
        self._cf = ConfluenceEngine()
        self._candles: list[LsmCandle] = []
        self._last_conf_result = None

    def process_candle(self, hc: HistoricalCandle) -> tuple[dict[str, Any], Any]:
        lc = hc_to_lsm(hc)
        self._candles.append(lc)
        if len(self._candles) > 100:
            self._candles.pop(0)

        self._sd.add_candle(lc)

        swing_highs = [s for s in self._sd._swing_points if str(s.swing_type) == "SwingType.SWING_HIGH"]
        swing_lows = [s for s in self._sd._swing_points if str(s.swing_type) == "SwingType.SWING_LOW"]

        zones = self._ld.analyze(
            swing_highs=swing_highs, swing_lows=swing_lows,
            equal_highs=[], equal_lows=[],
            current_price=lc.close, candles=self._candles,
        )
        sweeps = self._swd.analyze(candles=self._candles, liquidity_zones=zones)
        structure_events = self._ms.analyze(swing_highs=swing_highs, swing_lows=swing_lows, candles=self._candles)
        fvgs = self._fvg.analyze(self._candles)
        order_blocks = self._ob.analyze(self._candles, fvgs)
        pd_state = self._pd.analyze(swing_highs, swing_lows, lc.close)
        disp_obj = self._disp.analyze(self._candles)
        displacements = [disp_obj] if disp_obj else []

        conf_result = self._cf.analyze(
            liquidity_zones=zones, sweeps=sweeps,
            structure_events=structure_events, fvgs=fvgs,
            order_blocks=order_blocks, premium_discount=pd_state,
            displacements=displacements,
        )
        self._last_conf_result = conf_result

        bias = conf_result.directional_bias
        direction_str = bias.value if isinstance(bias, DirectionalBias) else str(bias)

        is_long = direction_str == "LONG"
        is_short = direction_str == "SHORT"

        lsm_data = {
            "direction": direction_str,
            "confluence_score": conf_result.confluence_score,
            "trade_permission": conf_result.trade_permission.value if hasattr(conf_result.trade_permission, "value") else str(conf_result.trade_permission),
            "swing_highs": swing_highs, "swing_lows": swing_lows,
            "sweeps": sweeps, "structure_events": structure_events,
            "fvgs": fvgs, "order_blocks": order_blocks,
            "risk_score": max(0, 1.0 - conf_result.directional_confidence) if not is_long and not is_short else 0.0,
            "sweep_bias": 1.0 if is_long else (-1.0 if is_short else 0.0),
            "structure_bias": 1.0 if is_long else (-1.0 if is_short else 0.0),
            "fvg_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "order_block_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "premium_discount_bias": -0.5 if is_long else (0.5 if is_short else 0.0),
            "displacement_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "microstructure_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "orderflow_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "trend_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "conflict_severity": "HIGH" if conf_result.conflict_score >= 0.6 else ("MEDIUM" if conf_result.conflict_score >= 0.3 else "NONE"),
        }
        return lsm_data, conf_result


def compute_metrics(trades: list) -> dict[str, Any]:
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "expectancy": 0, "profit_factor": 0, "avg_trades_per_day": 0}
    wins = [t for t in trades if t.net_r > 0]
    losses = [t for t in trades if t.net_r <= 0]
    total_r = sum(t.net_r for t in trades)
    gross_profit = sum(t.net_r for t in wins)
    gross_loss = abs(sum(t.net_r for t in losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else 99.0
    day_set = set()
    for t in trades:
        ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
        if ts:
            day_set.add(ts.strftime("%Y-%m-%d"))
    num_days = max(len(day_set), 1)
    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "expectancy": total_r / len(trades) if trades else 0,
        "profit_factor": pf,
        "avg_trades_per_day": len(trades) / num_days,
    }


def run_baseline(
    candles: list[HistoricalCandle],
    lsm_data_map: dict[int, dict],
    config: StrategyConfig,
    rcfg: ReplayConfig,
) -> dict[str, Any]:
    engine = StrategyEngine(config)
    sim = TradeSimulator(rcfg)
    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < rcfg.warmup_candles:
            continue
        lsm_data = lsm_data_map.get(i, {})
        direction_str = lsm_data.get("direction", "NEUTRAL")
        if direction_str == "NEUTRAL":
            continue
        direction = TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT
        entry = candle.close
        cr = candle.high - candle.low
        stop = candle.close - cr * 1.5 if direction == TradeDirection.LONG else candle.close + cr * 1.5
        target = candle.close + cr * 1.5 * 3.0 if direction == TradeDirection.LONG else candle.close - cr * 1.5 * 3.0
        lsm_data["direction"] = direction_str
        candidate = engine.evaluate(candle=candle, lsm_data=lsm_data, direction=direction, entry_price=entry, stop_loss=stop, target_price=target)
        if candidate is None:
            continue
        plan = TradePlan(
            plan_id=f"BP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
            direction=direction, signal_time=candle.timestamp,
            entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
            stop_loss=stop, target_price=target,
            plan_reason=f"Baseline confidence={candidate.total_confidence:.1f}",
        )
        sim.process_candle(hc_to_lsm(candle), [plan])
    return compute_metrics(sim.completed_trades)


def run_selective(
    candles: list[HistoricalCandle],
    lsm_data_map: dict[int, dict],
    conf_map: dict[int, Any],
    config: StrategyConfig,
    rcfg: ReplayConfig,
    mode: str = "real",
) -> tuple[dict[str, Any], RejectionReasonAnalyzer, dict[str, int]]:
    engine = StrategyEngine(config)
    sim = TradeSimulator(rcfg)
    ranker = CandidateRanker()
    qg = QualityGate(QualityGateConfig())
    sel = DailySelector(qg, DailySelectorConfig(target_trades_per_day=3, hard_max_per_day=4))
    ra = RejectionReasonAnalyzer()

    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < rcfg.warmup_candles:
            continue

        lsm_data = lsm_data_map.get(i, {})
        conf_result = conf_map.get(i)
        direction_str = lsm_data.get("direction", "NEUTRAL")

        if mode == "inverted":
            direction_str = "SHORT" if direction_str == "LONG" else ("LONG" if direction_str == "SHORT" else "NEUTRAL")

        if direction_str == "NEUTRAL":
            continue

        direction = TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT
        entry = candle.close
        cr = candle.high - candle.low
        stop = candle.close - cr * 1.5 if direction == TradeDirection.LONG else candle.close + cr * 1.5
        target = candle.close + cr * 1.5 * 3.0 if direction == TradeDirection.LONG else candle.close - cr * 1.5 * 3.0

        lsm_data["direction"] = direction_str
        candidate = engine.evaluate(candle=candle, lsm_data=lsm_data, direction=direction, entry_price=entry, stop_loss=stop, target_price=target)
        if candidate is None:
            continue

        if mode == "neutral":
            opp_dir_str = "SHORT" if direction_str == "LONG" else "LONG"
            opp_dir = TradeDirection.SHORT if direction == TradeDirection.LONG else TradeDirection.LONG
            opp_stop = candle.close + cr * 1.5 if opp_dir == TradeDirection.SHORT else candle.close - cr * 1.5
            opp_target = candle.close - cr * 1.5 * 3.0 if opp_dir == TradeDirection.SHORT else candle.close + cr * 1.5 * 3.0
            opp_lsm = dict(lsm_data)
            opp_lsm["direction"] = opp_dir_str
            opp_candidate = engine.evaluate(candle=candle, lsm_data=opp_lsm, direction=opp_dir, entry_price=entry, stop_loss=opp_stop, target_price=opp_target)
            if opp_candidate is not None:
                opp_rc = ranker.rank(opp_candidate, conf_result)
                rc = ranker.rank(candidate, conf_result)
                if opp_rc.rank_score > rc.rank_score:
                    candidate = opp_candidate
                    direction = opp_dir
                    direction_str = opp_dir_str
                    stop = opp_stop
                    target = opp_target

        rc = ranker.rank(candidate, conf_result)
        sel.register_candidate(rc)
        day_key = candle.timestamp.strftime("%Y-%m-%d")
        results = sel.select_for_day(day_key)

        for rc2, sr in results:
            if not sr.allowed:
                ra.record(rc2.candidate_id, sr.rejection_category, sr.rejection_reason)
                continue
            plan = TradePlan(
                plan_id=f"SP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                direction=direction, signal_time=candle.timestamp,
                entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
                stop_loss=stop, target_price=target,
                plan_reason=f"Selectivity rank={rc2.rank_score:.0f} grade={rc2.rank_grade}",
            )
            trades = sim.process_candle(hc_to_lsm(candle), [plan])
            for t in trades:
                sel.record_outcome(getattr(t, "trade_id", rc2.candidate_id), t.net_r > 0, day_key)

    daily_breakdown = defaultdict(int)
    for t in sim.completed_trades:
        ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
        if ts:
            daily_breakdown[ts.strftime("%Y-%m-%d")] += 1

    return compute_metrics(sim.completed_trades), ra, dict(daily_breakdown)


def precompute_lsm_data(candles: list[HistoricalCandle], warmup: int) -> tuple[dict[int, dict], dict[int, Any]]:
    """Run LSM pipeline once, store lsm_data + ConfluenceResult per candle index."""
    pipeline = RealTimeLsmPipeline()
    data_map: dict[int, dict] = {}
    conf_map: dict[int, Any] = {}
    total = len(candles)
    for i, c in enumerate(candles):
        data_map[i], conf_map[i] = pipeline.process_candle(c)
        if (i + 1) % 500 == 0:
            print(f"  LSM pipeline: {i+1}/{total}")
    print(f"  LSM pipeline: {total}/{total} complete")
    return data_map, conf_map


def main():
    print("Loading BTCUSDT 15m data...")
    candles = load_candles(HISTORICAL_DATA)
    print(f"Loaded {len(candles)} candles\n")

    rcfg = ReplayConfig(
        warmup_candles=50, taker_fee_percent=0.04,
        slippage_percent=0.02, funding_per_candle_percent=0.001,
    )
    strategy_config = StrategyConfig(confidence_threshold=60.0)

    print("Pre-computing LSM pipeline data...")
    lsm_data_map, conf_map = precompute_lsm_data(candles, rcfg.warmup_candles)
    print()

    print("--- Baseline Replay ---")
    base = run_baseline(candles, lsm_data_map, strategy_config, rcfg)
    print(f"  Trades: {base['total_trades']}, WR: {base['win_rate']*100:.1f}%, EV: {base['expectancy']:.2f}R, PF: {base['profit_factor']:.2f}, Avg/day: {base['avg_trades_per_day']:.1f}\n")

    modes = {"real": "Real Direction", "inverted": "Inverted Diagnostic", "neutral": "Neutral (Best of Both)"}
    results = {}

    for key, label in modes.items():
        print(f"--- Selective: {label} ---")
        metrics, ra, db = run_selective(candles, lsm_data_map, conf_map, strategy_config, rcfg, mode=key)
        results[key] = (metrics, ra, db)
        print(f"  Trades: {metrics['total_trades']}, WR: {metrics['win_rate']*100:.1f}%, EV: {metrics['expectancy']:.2f}R, PF: {metrics['profit_factor']:.2f}, Avg/day: {metrics['avg_trades_per_day']:.1f}\n")

    for key, label in modes.items():
        metrics, ra, db = results[key]
        print(SelectivityReport.generate(base, metrics, ra.stats, db, label=label))
        print()

    print("DONE.")


if __name__ == "__main__":
    main()
