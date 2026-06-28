"""Phase 5 — Forward test runner for frozen configuration.

Runs the exact frozen pipeline (A+ regime gate, atr14_20 stop, immediate entry)
on fresh unseen test windows. Collects every trade outcome, rejection reason,
and signal context.

Execution disabled by default (DRY_RUN=True) to prevent accidental live
execution.
"""

import json, os, sys, uuid
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab.replay_runner import (
    run_selective_replay_with_regime, ensure_data,
)
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.regime_filter import RegimeGate


FROZEN_CONFIG = FrozenConfig()
REPLAY_CFG = ReplayConfig(
    warmup_candles=50,
    taker_fee_percent=0.04,
    slippage_percent=0.02,
    funding_per_candle_percent=0.001,
)

# Frozen Phase 4 parameters (do not change)
STOP_METHOD = "atr14_20"
ENTRY_METHOD = "immediate"
TRAIN_DAYS = 30
TEST_DAYS = 30
STEP_DAYS = 30

DRY_RUN = True  # default disabled; set to False only after explicit approval


def run_forward_test(
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    data_days: int = 365,
    dry_run: bool = True,
    output_dir: str = "phase5_results",
) -> dict[str, Any]:
    """Execute forward test on the frozen configuration.

    Args:
        symbol: Trading pair symbol.
        timeframe: Candle timeframe.
        data_days: Days of historical data to load.
        dry_run: If True (default), logs intent but does not execute.
        output_dir: Directory for output files.

    Returns:
        Dict with trade_diagnostics, rejection_summary, window_metrics, and
        metadata.
    """
    if dry_run:
        print("[FORWARD TEST] DRY RUN — no trades executed.", flush=True)
        print(f"[FORWARD TEST] Config: stop={STOP_METHOD}, entry={ENTRY_METHOD}", flush=True)
        print(f"[FORWARD TEST] Symbol={symbol}, timeframe={timeframe}", flush=True)
        return {"status": "dry_run", "dry_run": True}

    os.makedirs(output_dir, exist_ok=True)

    candles = ensure_data(symbol, timeframe, days=data_days)
    end_ts = candles[-1].timestamp
    total_days = (end_ts - candles[0].timestamp).days

    all_trades: list[dict[str, Any]] = []
    all_rejections: list[dict[str, Any]] = []
    window_metrics: list[dict[str, Any]] = []

    for offset in range(0, total_days - TRAIN_DAYS - TEST_DAYS, STEP_DAYS):
        test_end = end_ts - timedelta(days=offset)
        test_start = test_end - timedelta(days=TEST_DAYS)
        train_start = test_start - timedelta(days=TRAIN_DAYS)
        train_end = test_start

        train_set = [c for c in candles if train_start <= c.timestamp < train_end]
        test_set = [c for c in candles if test_start <= c.timestamp < test_end]
        if len(train_set) < REPLAY_CFG.warmup_candles + 10 or len(test_set) < 10:
            continue

        gate = RegimeGate()
        gate.fit(train_set)

        try:
            metrics, ra, _, _ = run_selective_replay_with_regime(
                test_set, FROZEN_CONFIG, REPLAY_CFG, gate,
                diagnose=True, collect_trade_timestamps=True,
                stop_method=STOP_METHOD, entry_method=ENTRY_METHOD,
            )
        except Exception as e:
            print(f"[FORWARD TEST] Window error: {e}", flush=True)
            continue

        window_label = f"{test_start.strftime('%Y-%m-%d')}->{test_end.strftime('%Y-%m-%d')}"
        for d in metrics.get("trade_diagnostics", []):
            d["window"] = window_label
            d["test_start"] = test_start.isoformat()
            d["test_end"] = test_end.isoformat()
        all_trades.extend(metrics.get("trade_diagnostics", []))

        unique_rejected = len(set(cid for cid, _cat, _reason in ra.reasons))
        all_rejections.append({
            "window": window_label,
            "unique_rejected": unique_rejected,
            "total_reasons_recorded": len(ra.reasons),
        })

        wm = {
            "window": window_label,
            "total_trades": metrics.get("total_trades", 0),
            "win_rate": metrics.get("win_rate", 0),
            "expectancy": metrics.get("expectancy", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "max_drawdown_r": metrics.get("max_drawdown_r", 0),
            "total_signals": metrics.get("total_signals", 0),
            "rejected": metrics.get("rejected", 0),
        }
        window_metrics.append(wm)

    # Cumulative peak-to-trough DD across all trades (primary risk metric)
    cum = 0.0
    peak = 0.0
    cum_dd = 0.0
    for t in all_trades:
        cum += t.get("net_r", 0)
        peak = max(peak, cum)
        cum_dd = max(cum_dd, peak - cum)

    total_unique_rejected = sum(r.get("unique_rejected", 0) for r in all_rejections)

    result = {
        "status": "completed",
        "dry_run": False,
        "symbol": symbol,
        "timeframe": timeframe,
        "stop_method": STOP_METHOD,
        "entry_method": ENTRY_METHOD,
        "windows": len(window_metrics),
        "total_trades": len(all_trades),
        "total_unique_rejected": total_unique_rejected,
        "cumulative_max_dd_r": round(cum_dd, 2),
        "window_metrics": window_metrics,
        "trade_diagnostics": all_trades,
        "rejection_summary": all_rejections,
        "timestamp": datetime.now().isoformat(),
    }

    path = os.path.join(output_dir, "forward_test_result.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[FORWARD TEST] Saved {len(all_trades)} trades to {path}", flush=True)

    return result
