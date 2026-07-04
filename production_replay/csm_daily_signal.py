"""
Phase 80 — CSM Daily Signal
Generates daily cross-sectional momentum signals.
Outputs current long/short baskets with weights.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cross_sectional_momentum import (
    get_eligible_symbols, rank_by_momentum, generate_baskets, get_current_signal
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
SIGNAL_JSON = os.path.join(RESULTS_DIR, "csm_daily_signal.json")
SIGNAL_TXT = os.path.join(RESULTS_DIR, "csm_daily_signal.txt")

# Default basket sizes
DEFAULT_VARIANTS = [
    {"label": "top3_bottom3", "top_n": 3, "bottom_n": 3},
    {"label": "top5_bottom5", "top_n": 5, "bottom_n": 5},
    {"label": "top10_bottom10", "top_n": 10, "bottom_n": 10},
    {"label": "top15_bottom15", "top_n": 15, "bottom_n": 15},
]


def run_daily_signal():
    """Generate daily CSM signals for all variants.
    Returns report dict.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    eligible = get_eligible_symbols()
    ranked = rank_by_momentum(eligible)

    # Print top/bottom momentum for debugging
    print(f"Eligible: {len(eligible)}  Ranked: {len(ranked)}")
    if ranked:
        print(f"Top momentum:    {ranked[0][0]} {ranked[0][1]:+.4f}")
        print(f"Bottom momentum: {ranked[-1][0]} {ranked[-1][1]:+.4f}")

    variants = []
    for v in DEFAULT_VARIANTS:
        baskets = generate_baskets(ranked, v["top_n"], v["bottom_n"])
        variants.append({
            "label": v["label"],
            "top_n": v["top_n"],
            "bottom_n": v["bottom_n"],
            "long_basket": baskets.get("long_basket", []),
            "short_basket": baskets.get("short_basket", []),
            "long_avg_momentum": baskets.get("long_avg_momentum", 0),
            "short_avg_momentum": baskets.get("short_avg_momentum", 0),
            "error": baskets.get("error"),
        })

    # Use top5_bottom5 as primary signal
    primary = variants[1] if len(variants) > 1 else variants[0]

    report = {
        "mode": "csm_daily_signal",
        "timestamp": now,
        "lookback_days": 30,
        "eligible_symbols": len(eligible),
        "ranked_symbols": len(ranked),
        "primary_variant": primary["label"],
        "primary_long": primary["long_basket"],
        "primary_short": primary["short_basket"],
        "variants": variants,
        "live_trading": "NO",
        "real_orders": "NO",
    }

    # Write reports
    with open(SIGNAL_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    _write_txt_report(report)
    return report


def _write_txt_report(report):
    """Write human-readable TXT report."""
    lines = []
    lines.append("=" * 60)
    lines.append("CSM DAILY SIGNAL")
    lines.append(f"  {report['timestamp']}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Lookback:          {report['lookback_days']} days")
    lines.append(f"  Eligible Symbols:  {report['eligible_symbols']}")
    lines.append(f"  Ranked Symbols:    {report['ranked_symbols']}")
    lines.append(f"  Primary Variant:   {report['primary_variant']}")
    lines.append("")

    lines.append("  CURRENT LONG BASKET:")
    for i, s in enumerate(report.get("primary_long", []), 1):
        lines.append(f"    {i}. {s['symbol']:15s} mom={s['momentum_30d']:+.4f}  close={s['close']:.6f}")
    lines.append("")
    lines.append("  CURRENT SHORT BASKET:")
    for i, s in enumerate(report.get("primary_short", []), 1):
        lines.append(f"    {i}. {s['symbol']:15s} mom={s['momentum_30d']:+.4f}  close={s['close']:.6f}")
    lines.append("")

    lines.append("  ALL VARIANTS:")
    for v in report.get("variants", []):
        lines.append(f"    {v['label']:15s}  Long: {len(v['long_basket'])}  Short: {len(v['short_basket'])}")
    lines.append("")

    lines.append("  SAFETY:")
    lines.append(f"    Live Trading: NO")
    lines.append(f"    Real Orders:  NO")
    lines.append(f"    Execution:    read_only")
    lines.append("")
    lines.append("  WARNING: Paper signal only. No real orders placed.")
    lines.append("=" * 60)

    with open(SIGNAL_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    report = run_daily_signal()
    print(f"\nPrimary: {report['primary_variant']}")
    print(f"Long:  {[s['symbol'] for s in report['primary_long']]}")
    print(f"Short: {[s['symbol'] for s in report['primary_short']]}")
