"""BB Bounce Signal Generator.

Scans latest candles for Bollinger Band bounce setups.
Produces actionable signals for breadwinner daily report.
This module NEVER places real orders, NEVER enables live trading.
"""
import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.breadwinner_strategy_library import detect_bb_bounce

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
CACHE_DIR = os.path.join(STATE_DIR, "candles_cache")
JSON_PATH = os.path.join(RESULTS_DIR, "bb_signal_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "bb_signal_report.txt")
ALL_SIGNALS_PATH = os.path.join(RESULTS_DIR, "bb_all_signals.json")


def _load_candles(symbol: str, timeframe: str) -> list[dict]:
    path = os.path.join(CACHE_DIR, f"{symbol}_{timeframe}.json")
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _get_symbols() -> list[str]:
    symbols = []
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith("_1h.json"):
                sym = f.replace("_1h.json", "")
                symbols.append(sym)
    return sorted(symbols)


def scan_bb_signals(symbols: list[str], timeframe: str = "1h",
                    period: int = 15, std_mult: float = 3.5,
                    rr_target: float = 10.0,
                    min_entry_volume_ratio: float = 0.0) -> list[dict]:
    """Scan all symbols for BB bounce setups on the latest complete candle."""
    signals = []
    for sym in symbols:
        candles = _load_candles(sym, timeframe)
        if len(candles) < period + 5:
            continue
        seen_dir = set()
        for i in range(len(candles) - 3, len(candles) - 1):
            if i >= len(candles) - 1:
                continue
            sig = detect_bb_bounce(candles, i, period, std_mult, rr_target,
                                   min_entry_volume_ratio=min_entry_volume_ratio)
            if sig:
                sig["symbol"] = sym
                sig["timeframe"] = timeframe
                sig["detected_at"] = str(i)
                sig["live_ready"] = True
                sig["live_trading"] = False
                sig["paper_only"] = True
                dir_key = (sym, sig.get("direction", ""))
                if dir_key in seen_dir:
                    continue
                seen_dir.add(dir_key)
                signals.append(sig)
    return signals


def main():
    print("=" * 60)
    print("BB BOUNCE SIGNAL GENERATOR")
    print("=" * 60)

    symbols = _get_symbols()
    print(f"Symbols: {len(symbols)}")

    bb_signals = scan_bb_signals(symbols, min_entry_volume_ratio=1.5)
    print(f"\nBB Bounce signals: {len(bb_signals)}")
    for s in bb_signals[:10]:
        print(f"  {s['symbol']:20s} {s['direction']:5s} entry={s['entry']:.4f} "
              f"stop={s['stop']:.4f} target={s['target']:.4f} "
              f"entry_vol={s.get('entry_volume_ratio',0):.2f}x")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_scanned": len(symbols),
        "bb_bounce": {
            "signals": len(bb_signals),
            "config": "p=15 s=3.5 rr=10.0 stop=0.5% entry_vol>=1.5x no_max_hold",
            "top_signals": bb_signals[:5],
        },
        "total_signals": len(bb_signals),
        "live_trading": "NO",
        "paper_only": "YES",
    }

    all_signals = {
        "timestamp": report["timestamp"],
        "bb_bounce": bb_signals,
        "total": len(bb_signals),
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)
    with open(ALL_SIGNALS_PATH, "w") as f:
        json.dump(all_signals, f, indent=2)
    with open(TXT_PATH, "w") as f:
        f.write(f"BB Signals ({report['timestamp']})\n")
        f.write(f"Symbols scanned: {report['symbols_scanned']}\n")
        f.write(f"BB Bounce: {report['bb_bounce']['signals']} signals\n")
        f.write(f"Total: {report['total_signals']} signals (paper only)\n")

    print(f"\nReport saved to {JSON_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
