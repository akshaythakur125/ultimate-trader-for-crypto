#!/usr/bin/env python3
"""Phase 3 Prompt 8: Long-History Data Expansion + Walk-Forward Proof.

Downloads long OHLCV history, runs full robustness validation with
minimum evidence rules, and produces A+ only and A+ + governor verdicts.

Usage:
    python scripts/run_robustness_validation.py
"""

import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(line_buffering=True)

from ultimate_trader.data_engine import BingXDownloader, DatasetRegistry, DataReport
from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab import (
    FrozenConfig, MultiPeriodReplay, SymbolRobustness, TimeframeRobustness,
    WalkForwardReplay, EdgeStabilityAnalyzer, RobustnessReport,
    ensure_data, run_selective_replay, run_selective_replay_with_governor,
    run_selective_replay_with_regime, run_selective_replay_with_regime_governor,
)
from ultimate_trader.regime_filter import RegimeGate, RegimeGateConfig, RegimeClassifier, SimilarityScorer, ReferenceProfile


ALL_PAIRS = [
    ("BTCUSDT", "5m"), ("BTCUSDT", "15m"), ("BTCUSDT", "30m"), ("BTCUSDT", "1h"),
    ("ETHUSDT", "15m"), ("SOLUSDT", "15m"), ("BNBUSDT", "15m"), ("XRPUSDT", "15m"),
]


def download_all_data():
    """Download long-history data for all pairs."""
    downloader = BingXDownloader()
    registry = DatasetRegistry()

    print("=" * 70, flush=True)
    print("  STEP 1: DATA DOWNLOAD & VALIDATION")
    print("=" * 70, flush=True)

    for symbol, tf in ALL_PAIRS:
        if downloader.file_exists(symbol, tf):
            print(f"  {symbol} {tf}: found locally", flush=True)
        else:
            print(f"  {symbol} {tf}: downloading (target 365d)...", flush=True)
            result = downloader.download(symbol, tf, target_days=365)
            if result.success:
                print(f"    {result.candle_count} candles, {result.days_covered}d", flush=True)
            else:
                print(f"    FAILED: {result.error}", flush=True)
        info = registry.register(symbol, tf)
        print(f"    Status: {info.quality.value} — {info.reason}", flush=True)

    print(flush=True)
    print(DataReport.generate(registry), flush=True)
    return registry


def compute_symbol_concentration(symbol_results) -> float:
    """Compute max % of total net profit from a single symbol."""
    profits = {}
    total = 0
    for sr in symbol_results:
        if sr.data_available and sr.total_trades >= 5:
            p = sr.expectancy * sr.total_trades
            symbol = sr.symbol
            profits[symbol] = profits.get(symbol, 0) + p
            total += p
    if total <= 0:
        return 100.0
    max_sym_profit = max(profits.values()) if profits else 0
    return (max_sym_profit / total) * 100


def main():
    t_start = time.time()

    frozen = FrozenConfig()
    rcfg = ReplayConfig(
        warmup_candles=50, taker_fee_percent=0.04,
        slippage_percent=0.02, funding_per_candle_percent=0.001,
    )

    # ---- 1. Download & validate data ----
    registry = download_all_data()
    dataset_lines = []
    for d in sorted(registry.datasets, key=lambda x: (x.symbol, x.timeframe)):
        status = d.quality.value
        dataset_lines.append(f"  {d.symbol} {d.timeframe}: {d.candle_count}c, "
                             f"{d.days_covered:.0f}d, {status}")

    # ---- 2. BTC Multi-Period (long history) ----
    print("\nB. BTC Multi-Period Replay", flush=True)
    print("=" * 50, flush=True)
    mp = MultiPeriodReplay(frozen, rcfg)
    mp.run("BTCUSDT", "15m")

    # ---- 3. Symbol Robustness ----
    print("\nC. Symbol Robustness", flush=True)
    print("=" * 50, flush=True)
    sr_class = SymbolRobustness(frozen, rcfg)
    sr_class.run()

    # ---- 4. Timeframe Robustness ----
    print("\nD. Timeframe Robustness", flush=True)
    print("=" * 50, flush=True)
    tr_class = TimeframeRobustness(frozen, rcfg)
    tr_class.run()

    # ---- 5. Walk-Forward: A+ only ----
    print("\nE. Walk-Forward Replay (A+ selectivity only)", flush=True)
    print("=" * 50, flush=True)
    wf = WalkForwardReplay(frozen)
    wf.run(symbol="BTCUSDT", timeframe="15m", run_governor=False)

    # ---- 6. Walk-Forward: A+ + governor ----
    print("\nE2. Walk-Forward Replay (A+ + risk governor)", flush=True)
    print("=" * 50, flush=True)
    wf_gov = WalkForwardReplay(frozen)
    wf_gov.run(symbol="BTCUSDT", timeframe="15m", run_governor=True)

    # ---- 6b. Walk-Forward: A+ + regime gate ----
    print("\nE3. Walk-Forward Replay (A+ + regime gate)", flush=True)
    print("=" * 50, flush=True)
    wf_reg = WalkForwardReplay(frozen)
    wf_reg.run(symbol="BTCUSDT", timeframe="15m", run_regime=True)

    # ---- 6c. Walk-Forward: A+ + regime + governor ----
    print("\nE4. Walk-Forward Replay (A+ + regime + governor)", flush=True)
    print("=" * 50, flush=True)
    wf_reg_gov = WalkForwardReplay(frozen)
    wf_reg_gov.run(symbol="BTCUSDT", timeframe="15m", run_regime_governor=True)

    # ---- 7. Run A+ + governor on full dataset for aggregate metrics ----
    print("\nF. A+ + Governor Full Dataset Replay", flush=True)
    print("=" * 50, flush=True)
    btc_candles = ensure_data("BTCUSDT", "15m")
    gov_cfg = None
    after_gov_metrics = {"total_trades": 0, "win_rate": 0, "expectancy": 0,
                          "profit_factor": 0, "avg_trades_per_day": 0, "max_drawdown": 0}
    if btc_candles:
        metrics, ra, db, gov_stats = run_selective_replay_with_governor(
            btc_candles, frozen, rcfg, gov_cfg,
        )
        after_gov_metrics = metrics
        print(f"  Trades: {metrics['total_trades']}, WR {metrics['win_rate']*100:.1f}%, "
              f"EV {metrics['expectancy']:.2f}R, PF {metrics['profit_factor']:.2f}, "
              f"DD {metrics['max_drawdown']:.1f}R", flush=True)
        print(f"  Blocked: {sum(gov_stats.values())} "
              f"(consec={gov_stats['consecutive_losses']}, "
              f"DDmode={gov_stats['drawdown_mode']})", flush=True)

    # ---- 7b. Run A+ + regime gate on full dataset ----
    print("\nF2. A+ + Regime Gate Full Dataset Replay", flush=True)
    print("=" * 50, flush=True)
    regime_gated_metrics = {}
    if btc_candles:
        # Use last 60 days (5760 candles of 15m) as the profitable regime reference
        ref_window = min(5760, len(btc_candles))
        reg_cfg = RegimeGateConfig(reference_window_candles=ref_window)
        regime_gate = RegimeGate(reg_cfg)
        regime_gate.fit(btc_candles)
        reg_metrics, _, _, reg_stats = run_selective_replay_with_regime(
            btc_candles, frozen, rcfg, regime_gate,
        )
        regime_gated_metrics = reg_metrics
        scores = reg_stats.get("regime_scores", [])
        avg_score = sum(scores) / len(scores) if scores else 0
        print(f"  Trades: {reg_metrics['total_trades']}, WR {reg_metrics['win_rate']*100:.1f}%, "
              f"EV {reg_metrics['expectancy']:.2f}R, PF {reg_metrics['profit_factor']:.2f}, "
              f"DD {reg_metrics['max_drawdown']:.1f}R", flush=True)
        print(f"  Regime blocked: {reg_stats.get('regime_blocked', 0)}, "
              f"avg score: {avg_score:.1f}, ref window: {ref_window} candles", flush=True)

    # ---- 7c. Run A+ + regime + governor on full dataset ----
    print("\nF3. A+ + Regime + Governor Full Dataset Replay", flush=True)
    print("=" * 50, flush=True)
    regime_governor_metrics = {}
    if btc_candles:
        ref_window2 = min(5760, len(btc_candles))
        reg_cfg2 = RegimeGateConfig(reference_window_candles=ref_window2)
        regime_gate2 = RegimeGate(reg_cfg2)
        regime_gate2.fit(btc_candles)
        rg_metrics, _, _, rg_gov_stats, rg_stats = run_selective_replay_with_regime_governor(
            btc_candles, frozen, rcfg, regime_gate2, None,
        )
        regime_governor_metrics = rg_metrics
        total_checked = max(len(rg_stats.get("regime_scores", [])), 1)
        regime_governor_metrics["regime_block_pct"] = (
            rg_stats.get("regime_blocked", 0) / total_checked * 100
        )
        scores2 = rg_stats.get("regime_scores", [])
        avg_score2 = sum(scores2) / len(scores2) if scores2 else 0
        print(f"  Trades: {rg_metrics['total_trades']}, WR {rg_metrics['win_rate']*100:.1f}%, "
              f"EV {rg_metrics['expectancy']:.2f}R, PF {rg_metrics['profit_factor']:.2f}, "
              f"DD {rg_metrics['max_drawdown']:.1f}R", flush=True)
        print(f"  Gov blocked: {sum(rg_gov_stats.values())}, "
              f"Regime blocked: {rg_stats.get('regime_blocked', 0)}, "
              f"avg score: {avg_score2:.1f}", flush=True)

    # ---- 8. Compute symbol concentration ----
    max_symbol_pct = compute_symbol_concentration(sr_class.results)

    # ---- 9. Edge Stability ----
    total_oos_trades = 0
    for pr in mp.results:
        total_oos_trades += pr.total_trades
    for s in sr_class.results:
        if s.data_available:
            total_oos_trades += s.total_trades
    for t in tr_class.results:
        if t.data_available:
            total_oos_trades += t.total_trades
    for w in wf.windows:
        total_oos_trades += w.test_trades

    analyzer = EdgeStabilityAnalyzer()
    edge = analyzer.classify(
        mp.results, sr_class.results, tr_class.results,
        wf.windows, total_oos_trades,
        after_governor_metrics=after_gov_metrics,
        governor_walk_forward_windows=wf_gov.governor_windows,
        max_symbol_profit_pct=max_symbol_pct,
        regime_gated_metrics=regime_gated_metrics,
        regime_governor_metrics=regime_governor_metrics,
    )

    # ---- 10. Report ----
    report = RobustnessReport.generate(
        frozen, mp.results, sr_class.results, tr_class.results,
        wf.windows, edge,
        dataset_quality_lines=dataset_lines,
        governor_walk_forward_windows=wf_gov.governor_windows,
        after_governor_metrics=after_gov_metrics,
        regime_gated_metrics=regime_gated_metrics,
        regime_governor_metrics=regime_governor_metrics,
        regime_walk_forward_windows=wf_reg.regime_windows,
        regime_governor_walk_forward_windows=wf_reg_gov.regime_governor_windows,
    )
    print(f"\n{report}", flush=True)
    print(f"\n  Elapsed: {time.time()-t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
