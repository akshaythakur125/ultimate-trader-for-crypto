#!/usr/bin/env python3
"""Phase 3 Prompt 3: Directional Bias Audit + Overtrading Control replay script.

Loads BTCUSDT 15m data, runs strategy replay, and produces:
- Bias audit summary (long/short win rate, direction accuracy)
- Component attribution (best/worst directional components)
- Inverse signal test (original vs inverted vs weak-blocked)
- Direction conflict analysis
- Trade frequency control simulation

Usage:
    python scripts/run_directional_audit.py
"""

import os
import sys
import csv
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.historical_replay.models import HistoricalCandle, TradeDirection
from ultimate_trader.strategy_engine.engine import run_strategy_replay
from ultimate_trader.strategy_engine.models import StrategyConfig
from ultimate_trader.backtest_forensics.diagnostic_builder import build_trade_diagnostics
from ultimate_trader.directional_diagnostics import (
    BiasAuditor,
    BiasComponentAttribution,
    InverseSignalTester,
    DirectionConflictDetector,
    TradeFrequencyController,
    DirectionalReplayReport,
)


HISTORICAL_DATA = os.path.join("data", "historical", "BTCUSDT_15m.csv")


def load_candles(path: str) -> list[HistoricalCandle]:
    candles = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                candle = HistoricalCandle(
                    symbol=row.get("symbol", "BTCUSDT"),
                    timeframe=row.get("timeframe", "15m"),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                )
                candles.append(candle)
            except (KeyError, ValueError) as e:
                continue
    return candles


def lsm_data_provider(candle, idx):
    seed = hash(f"{candle.timestamp}") & 0xFFFF
    r = (seed % 100) / 100.0
    is_long = r > 0.5
    return {
        "direction": "LONG" if is_long else "SHORT",
        "confluence_score": r * 100,
        "trade_permission": "ALLOW",
        "swing_highs": [],
        "swing_lows": [],
        "sweeps": [],
        "structure_events": [],
        "fvgs": [],
        "order_blocks": [],
        "risk_score": 0.2,
        "sweep_bias": 1.0 if is_long else -1.0,
        "structure_bias": 0.5 if is_long else -0.5,
        "fvg_bias": 0.5 if is_long else -0.5,
        "order_block_bias": 0.5 if is_long else -0.5,
        "premium_discount_bias": 0.5 if is_long else -0.5,
        "displacement_bias": 0.5 if is_long else -0.5,
        "microstructure_bias": 1.0 if is_long else -1.0,
        "orderflow_bias": 0.5 if is_long else -0.5,
        "trend_bias": 0.5 if is_long else -0.5,
        "conflict_severity": "NONE",
    }


def run_audit():
    print("Loading BTCUSDT 15m data...")
    candles = load_candles(HISTORICAL_DATA)
    print(f"Loaded {len(candles)} candles\n")

    print("Running strategy replay...")
    config = StrategyConfig(
        confidence_threshold=60.0,
        direction=TradeDirection.LONG,
    )
    candidates, trades, sim = run_strategy_replay(
        candles, lsm_data_provider, config
    )
    print(f"Candidates evaluated: {len(candidates)}")
    print(f"Completed trades:  {len(trades)}")
    print()

    diagnostics = []
    for trade in trades:
        matching_cand = next(
            (c for c in candidates if c.timestamp == getattr(trade, "signal_time", None)),
            None,
        )
        td = build_trade_diagnostics(
            trade,
            strategy_candidate=matching_cand,
            candles_history=candles,
        )
        diagnostics.append(td)

    if not diagnostics:
        print("No trades to analyze.")
        return

    # ---- Bias Audit ----
    print("=" * 70)
    print("BIAS AUDIT")
    print("=" * 70)
    auditor = BiasAuditor()
    for td in diagnostics:
        auditor.audit_trade_diagnostics(td)
    bias_summary = auditor.summarize()
    print(f"  Total trades:     {bias_summary.total_trades}")
    print(f"  Long win rate:    {bias_summary.long_win_rate*100:.1f}%")
    print(f"  Short win rate:   {bias_summary.short_win_rate*100:.1f}%")
    print(f"  Direction acc:    {bias_summary.direction_accuracy*100:.1f}%")
    print(f"  Wrong dir rate:   {bias_summary.wrong_direction_rate*100:.1f}%")
    print(f"  Summary:          {bias_summary.audit_summary}")
    print()

    # ---- Component Attribution ----
    print("=" * 70)
    print("COMPONENT ATTRIBUTION")
    print("=" * 70)
    attributor = BiasComponentAttribution()
    trade_dicts = []
    for td in diagnostics:
        trade_dicts.append({
            "directional_components": td.directional_components,
            "net_r": td.net_r,
            "direction": td.direction.value,
            "is_winner": td.is_winner(),
        })
    attr_result = attributor.analyze(trade_dicts)
    print(f"  Helping:   {', '.join(attr_result.components_helping_direction[:5]) or 'none'}")
    print(f"  Hurting:   {', '.join(attr_result.components_hurting_direction[:5]) or 'none'}")
    print(f"  Unreliable: {', '.join(attr_result.unreliable_components[:5]) or 'none'}")
    print(f"  {attr_result.recommended_reweighting}")
    print()

    # ---- Inverse Signal Test ----
    print("=" * 70)
    print("INVERSE SIGNAL TEST")
    print("=" * 70)
    tester = InverseSignalTester(weak_confidence_threshold=70.0)
    inverse_trades = []
    for td in diagnostics:
        inverse_trades.append({
            "direction": td.direction.value,
            "net_r": td.net_r,
            "confidence": td.confidence_score or 60.0,
        })
    inv_result = tester.test_variants_simple(inverse_trades)
    print(f"  Original:       {inv_result.original_trades} trades, {inv_result.original_stats.get('win_rate',0):.1f}% WR, {inv_result.original_stats.get('expectancy',0):.2f}R")
    print(f"  Inverted:       {inv_result.inverted_trades} trades, {inv_result.inverted_stats.get('win_rate',0):.1f}% WR, {inv_result.inverted_stats.get('expectancy',0):.2f}R")
    print(f"  Weak-blocked:   {inv_result.weak_blocked_trades} trades, {inv_result.weak_blocked_stats.get('win_rate',0):.1f}% WR, {inv_result.weak_blocked_stats.get('expectancy',0):.2f}R")
    print()

    # ---- Direction Conflict Analysis ----
    print("=" * 70)
    print("DIRECTION CONFLICT ANALYSIS")
    print("=" * 70)
    detector = DirectionConflictDetector()
    conflicts = 0
    for td in diagnostics:
        comps = td.directional_components
        result = detector.detect(
            lsm_bias="LONG" if comps.get("sweep_bias", 0) > 0 else "SHORT" if comps.get("sweep_bias", 0) < 0 else "NEUTRAL",
            microstructure_bias="BULLISH" if comps.get("microstructure_bias", 0) > 0 else "BEARISH" if comps.get("microstructure_bias", 0) < 0 else "NEUTRAL",
            orderflow_bias="LONG" if comps.get("orderflow_bias", 0) > 0 else "SHORT" if comps.get("orderflow_bias", 0) < 0 else "NEUTRAL",
            strategy_bias=td.directional_vote,
        )
        if result.has_conflict:
            conflicts += 1
    print(f"  Trades with conflicts: {conflicts}/{len(diagnostics)}")
    print()

    # ---- Trade Frequency Control Simulation ----
    print("=" * 70)
    print("TRADE FREQUENCY CONTROL SIMULATION")
    print("=" * 70)
    ctrl = TradeFrequencyController(
        target_trades_per_day=4,
        hard_max_candidates_per_day=6,
        base_confidence_threshold=60.0,
    )
    original_count = len(inverse_trades)
    allowed_count = 0
    blocked_quota = 0
    blocked_cooldown = 0
    blocked_confidence = 0
    for t in inverse_trades:
        direction = t["direction"]
        confidence = t.get("confidence", 60.0)
        ts = datetime(2025, 1, 1)
        result = ctrl.check("BTCUSDT", direction, ts, confidence)
        if result.allowed:
            ctrl.record_trade("BTCUSDT", direction, ts, was_loss=t["net_r"] <= 0)
            allowed_count += 1
        else:
            if "quota" in result.rejection_reason:
                blocked_quota += 1
            elif "cooldown" in result.rejection_reason:
                blocked_cooldown += 1
            elif "confidence" in result.rejection_reason:
                blocked_confidence += 1
    print(f"  Original trades:       {original_count}")
    print(f"  After freq control:    {allowed_count}")
    print(f"  Blocked (quota):       {blocked_quota}")
    print(f"  Blocked (cooldown):    {blocked_cooldown}")
    print(f"  Blocked (confidence):  {blocked_confidence}")
    print()

    # ---- Full Report ----
    print(DirectionalReplayReport.generate(
        original_result={
            "total_trades": inv_result.original_trades,
            "win_rate": inv_result.original_stats.get("win_rate", 0),
            "expectancy": inv_result.original_stats.get("expectancy", 0),
            "profit_factor": inv_result.original_stats.get("profit_factor", 0),
            "avg_trades_per_day": original_count / 30.0,
        },
        inverted_result={
            "total_trades": inv_result.inverted_trades,
            "win_rate": inv_result.inverted_stats.get("win_rate", 0),
            "expectancy": inv_result.inverted_stats.get("expectancy", 0),
            "profit_factor": inv_result.inverted_stats.get("profit_factor", 0),
            "avg_trades_per_day": inv_result.inverted_trades / 30.0,
        },
        weak_blocked_result={
            "total_trades": inv_result.weak_blocked_trades,
            "win_rate": inv_result.weak_blocked_stats.get("win_rate", 0),
            "expectancy": inv_result.weak_blocked_stats.get("expectancy", 0),
            "profit_factor": inv_result.weak_blocked_stats.get("profit_factor", 0),
            "avg_trades_per_day": inv_result.weak_blocked_trades / 30.0,
        },
        attribution_result=attr_result,
        bias_summary=bias_summary,
        overtrading_reduced=(allowed_count < original_count),
    ))


if __name__ == "__main__":
    run_audit()
