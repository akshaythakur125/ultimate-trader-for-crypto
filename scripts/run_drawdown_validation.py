#!/usr/bin/env python3
"""Drawdown validation - runs only governor replays, uses cached baselines."""
import sys, os, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(line_buffering=True)

from ultimate_trader.historical_replay.models import ReplayConfig, TradeDirection, TradePlan
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator
from ultimate_trader.liquidity_smart_money import Candle as LsmCandle
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.selectivity_engine import CandidateRanker, DailySelector, DailySelectorConfig, QualityGate, QualityGateConfig
from ultimate_trader.strategy_engine.engine import StrategyEngine
from ultimate_trader.strategy_engine.models import StrategyConfig
from ultimate_trader.robustness_lab.replay_runner import ensure_data, hc_to_lsm, compute_metrics, _LsmPipeline
from ultimate_trader.drawdown_control import (
    RiskGovernor, RiskGovernorConfig,
    DrawdownAnalyzer, LossClusterAnalyzer, SymbolTimeframeAttribution,
    DrawdownReport,
)

# Baseline results from robustness validation (before governor)
BASELINE_METRICS = {
    "total_trades": 540, "win_rate": 0.401, "expectancy": 0.35, "profit_factor": 1.46, "max_drawdown": 25.5, "avg_trades_per_day": 1.35,
}

PAIRS = [
    ("BTCUSDT", "15m"), ("ETHUSDT", "15m"), ("SOLUSDT", "15m"),
    ("BNBUSDT", "15m"), ("XRPUSDT", "15m"),
    ("BTCUSDT", "5m"), ("BTCUSDT", "30m"), ("BTCUSDT", "1h"),
]


def run_gov_replay(candles, frozen, rcfg, gov_cfg):
    strat_cfg = StrategyConfig(confidence_threshold=frozen.strategy_confidence_threshold)
    engine = StrategyEngine(strat_cfg)
    sim = TradeSimulator(rcfg)
    ranker = CandidateRanker()
    qg_cfg = QualityGateConfig(
        min_confluence_score=frozen.min_confluence_score,
        min_directional_confidence=frozen.min_directional_confidence,
        max_conflict_score=frozen.max_conflict_score,
        max_reversal_risk_score=frozen.max_reversal_risk_score,
        max_risk_score=frozen.max_risk_score,
        min_rr=frozen.min_rr,
        allowed_grades=set(frozen.allowed_grades),
    )
    qg = QualityGate(qg_cfg)
    ds_cfg = DailySelectorConfig(
        target_trades_per_day=frozen.target_trades_per_day,
        hard_max_per_day=frozen.hard_max_per_day,
        same_symbol_cooldown_minutes=frozen.same_symbol_cooldown_minutes,
        same_direction_cooldown_minutes=frozen.same_direction_cooldown_minutes,
        loss_threshold_increase=frozen.loss_threshold_increase,
        max_losses_per_day=frozen.max_losses_per_day,
    )
    sel = DailySelector(qg, ds_cfg)
    gov = RiskGovernor(gov_cfg)
    gov_stats = {"daily_loss": 0, "weekly_loss": 0, "drawdown_mode": 0, "rolling_perf": 0, "consecutive_losses": 0}
    lsm = _LsmPipeline()
    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < rcfg.warmup_candles:
            lsm.process_candle(candle)
            continue
        lsm_data, conf_result = lsm.process_candle(candle)
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
        grade = getattr(candidate, "grade", "")
        rc = ranker.rank(candidate, conf_result)
        sel.register_candidate(rc)
        day_key = candle.timestamp.strftime("%Y-%m-%d")
        results = sel.select_for_day(day_key)
        for rc2, sr in results:
            if not sr.allowed:
                continue
            dec = gov.check_state(candle.timestamp, grade=grade)
            if not dec.allowed:
                if "daily loss" in dec.rejection_reason:
                    gov_stats["daily_loss"] += 1
                elif "weekly loss" in dec.rejection_reason:
                    gov_stats["weekly_loss"] += 1
                elif "DEFENSIVE" in dec.risk_mode or "CAPITAL" in dec.risk_mode:
                    gov_stats["drawdown_mode"] += 1
                elif "EV" in dec.rejection_reason or "PF" in dec.rejection_reason:
                    gov_stats["rolling_perf"] += 1
                elif "consecutive" in dec.rejection_reason:
                    gov_stats["consecutive_losses"] += 1
                else:
                    gov_stats["drawdown_mode"] += 1
                continue
            plan = TradePlan(
                plan_id=f"RP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                direction=direction, signal_time=candle.timestamp,
                entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
                stop_loss=stop, target_price=target,
            )
            trades = sim.process_candle(hc_to_lsm(candle), [plan])
            for t in trades:
                sel.record_outcome(getattr(t, "trade_id", rc2.candidate_id), t.net_r > 0, day_key)
                if t.net_r != 0.0:
                    gov.evaluate(t, grade=grade)
    return sim.completed_trades, gov_stats


def main():
    frozen = FrozenConfig()
    gov_cfg = RiskGovernorConfig()
    all_after_trades = []
    all_gov_stats = {"daily_loss": 0, "weekly_loss": 0, "drawdown_mode": 0, "rolling_perf": 0, "consecutive_losses": 0}
    grouped_trades = {}

    t_start = time.time()

    for symbol, tf in PAIRS:
        print(f"\n{'='*50}", flush=True)
        print(f"  {symbol} {tf}...", flush=True)
        candles = ensure_data(symbol, tf, days=90)
        if len(candles) < 60:
            print(f"  SKIP: {len(candles)} candles", flush=True)
            continue
        cfg_tf = ReplayConfig(
            warmup_candles={"5m": 100, "15m": 50, "30m": 30, "1h": 20}.get(tf, 50),
            taker_fee_percent=0.04, slippage_percent=0.02, funding_per_candle_percent=0.001,
        )
        t0 = time.time()
        trades, gs = run_gov_replay(candles, frozen, cfg_tf, gov_cfg)
        print(f"  -> {len(trades)} trades in {time.time()-t0:.0f}s", flush=True)
        all_after_trades.extend(trades)
        grouped_trades[(symbol, tf)] = trades
        for k, v in gs.items():
            all_gov_stats[k] += v

    print(f"\n{'='*50}", flush=True)
    print("  BEFORE GOVERNOR (cached from robustness run)", flush=True)
    print(f"    Trades: {BASELINE_METRICS['total_trades']}, WR {BASELINE_METRICS['win_rate']*100:.1f}%, EV {BASELINE_METRICS['expectancy']:.2f}R, PF {BASELINE_METRICS['profit_factor']:.2f}, DD {BASELINE_METRICS['max_drawdown']:.1f}R", flush=True)

    after_m = compute_metrics(all_after_trades)
    print(f"\n  AFTER GOVERNOR", flush=True)
    print(f"    Trades: {after_m['total_trades']}, WR {after_m['win_rate']*100:.1f}%, EV {after_m['expectancy']:.2f}R, PF {after_m['profit_factor']:.2f}, DD {after_m['max_drawdown']:.1f}R", flush=True)
    print(f"    Blocked: {sum(all_gov_stats.values())}", flush=True)

    da = DrawdownAnalyzer()
    dd_info = da.analyze(all_after_trades)
    lca = LossClusterAnalyzer()
    lc_info = lca.analyze(all_after_trades)

    sta = SymbolTimeframeAttribution()
    total_net = sum(t.net_r for t in all_after_trades)
    attr = sta.analyze(grouped_trades, total_net, after_m.get("max_drawdown", 0))

    worst_attr = max(attr, key=lambda r: r.max_drawdown) if attr else None
    if worst_attr:
        main_cause = f"Worst DD from {worst_attr.symbol} {worst_attr.timeframe} ({worst_attr.max_drawdown:.1f}R)"
    elif dd_info.get("largest_episode"):
        main_cause = dd_info["largest_episode"]["cause"]
    else:
        main_cause = "unknown"
    print(f"\n  Main DD cause: {main_cause}", flush=True)

    reduction = (1 - after_m["max_drawdown"] / BASELINE_METRICS["max_drawdown"]) * 100 if BASELINE_METRICS["max_drawdown"] > 0 else 0

    if after_m["total_trades"] < 50:
        verdict = "INSUFFICIENT_TRADES"
    elif after_m["max_drawdown"] > 5.0:
        verdict = "DRAWDOWN_TOO_HIGH"
    elif after_m["expectancy"] > 0 and after_m["profit_factor"] > 1.2 and after_m["avg_trades_per_day"] <= 4:
        verdict = "PROMISING_BUT_UNPROVEN" if reduction >= 30 else "OVERFIT_SUSPECTED"
    else:
        verdict = "NO_EDGE"

    report = DrawdownReport.generate(
        BASELINE_METRICS, after_m, all_gov_stats, attr,
        dd_info.get("largest_episode", {}), lc_info, verdict,
    )
    print(f"\n{report}", flush=True)
    print(f"\n  Elapsed: {time.time()-t_start:.0f}s", flush=True)
    print(f"  Main cause of 25.5R drawdown: {main_cause}", flush=True)


if __name__ == "__main__":
    main()
