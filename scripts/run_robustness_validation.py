#!/usr/bin/env python3
"""Phase 3 Prompt 6: Out-of-Sample Robustness Validation.

Usage:
    python scripts/run_robustness_validation.py
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab import (
    FrozenConfig, MultiPeriodReplay, SymbolRobustness, TimeframeRobustness,
    WalkForwardReplay, EdgeStabilityAnalyzer, RobustnessReport,
    ensure_data, run_selective_replay,
)


def main():
    frozen = FrozenConfig()
    rcfg = ReplayConfig(
        warmup_candles=50, taker_fee_percent=0.04,
        slippage_percent=0.02, funding_per_candle_percent=0.001,
    )

    total_oos_trades = 0

    # ---- B. BTC Multi-Period ----
    print("\nB. BTC Multi-Period Replay")
    print("=" * 50)
    mp = MultiPeriodReplay(frozen, rcfg)
    mp.run("BTCUSDT", "15m")

    # ---- C. Symbol Robustness ----
    print("\nC. Symbol Robustness")
    print("=" * 50)
    sr = SymbolRobustness(frozen, rcfg)
    sr.run()

    # ---- D. Timeframe Robustness ----
    print("\nD. Timeframe Robustness")
    print("=" * 50)
    tr = TimeframeRobustness(frozen, rcfg)
    tr.run()

    # ---- E. Walk-Forward ----
    print("\nE. Walk-Forward Replay")
    print("=" * 50)
    wf = WalkForwardReplay(frozen)
    wf.run()

    # Compute total OOS trades
    for pr in mp.results:
        if "Last 30" in pr.label:
            total_oos_trades += pr.total_trades
    for s in sr.results:
        if s.data_available:
            total_oos_trades += s.total_trades
    for t in tr.results:
        if t.data_available:
            total_oos_trades += t.total_trades
    for w in wf.windows:
        total_oos_trades += w.test_trades

    # ---- F. Edge Stability ----
    analyzer = EdgeStabilityAnalyzer()
    edge = analyzer.classify(mp.results, sr.results, tr.results, wf.windows, total_oos_trades)

    # ---- Report ----
    report = RobustnessReport.generate(frozen, mp.results, sr.results, tr.results, wf.windows, edge)
    print("\n" + report)


if __name__ == "__main__":
    main()
