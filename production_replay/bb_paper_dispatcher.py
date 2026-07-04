"""BB Bounce Paper Trade Dispatcher.

Converts BB Bounce live signals into paper trade candidates for the
paper rotation engine.

This module NEVER places real orders, NEVER enables live trading.
"""
import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
ALL_SIGNALS_PATH = os.path.join(RESULTS_DIR, "bb_all_signals.json")
CANDIDATES_PATH = os.path.join(RESULTS_DIR, "bb_candidates.json")
PORTFOLIO_PATH = os.path.join(STATE_DIR, "paper_portfolio.json")

THESIS_SCORE_BB = 80


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_portfolio() -> list[dict]:
    data = _read_json(PORTFOLIO_PATH)
    return data if isinstance(data, list) else []


def _get_active_symbols(portfolio: list[dict]) -> set:
    return set(
        t.get("symbol", "")
        for t in portfolio
        if t.get("status") == "PAPER_OPEN"
    )


def _signal_to_candidate(sig: dict) -> dict:
    direction = sig.get("direction", "LONG")
    side = "LONG" if direction.upper() == "LONG" else "SHORT"
    entry = float(sig.get("entry", 0))
    stop = float(sig.get("stop", 0))
    target = float(sig.get("target", 0))
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0

    return {
        "symbol": sig.get("symbol", ""),
        "timeframe": sig.get("timeframe", "1h"),
        "direction": side,
        "side": side,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
        "thesis_type": "BB_BOUNCE",
        "strategy_family": "bb_bounce_v1",
        "pattern_name": sig.get("pattern", "bb_bounce_v1"),
        "trigger_status": "TRIGGER_CONFIRMED",
        "thesis_score": THESIS_SCORE_BB,
        "raw_anomaly_score": THESIS_SCORE_BB,
        "bucket": "bb_signal",
        "reason": f"bb_bounce_v1 signal on {sig.get('symbol','')} {side}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "live_ready": True,
        "live_trading": False,
        "paper_only": True,
    }


def _dedup_candidates(candidates: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for c in candidates:
        key = (c.get("symbol", ""), c.get("direction", ""), round(c.get("entry", 0), 6))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped


def dispatch_paper_candidates() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    portfolio = _read_portfolio()
    active_symbols = _get_active_symbols(portfolio)
    all_signals = _read_json(ALL_SIGNALS_PATH)

    raw_candidates = []

    bb_signals = all_signals.get("bb_bounce", [])
    for sig in bb_signals:
        if sig.get("symbol", "") in active_symbols:
            continue
        raw_candidates.append(_signal_to_candidate(sig))

    candidates = _dedup_candidates(raw_candidates)

    result = {
        "mode": "bb_paper_dispatcher",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "signals_loaded": {
            "bb_bounce": len(bb_signals),
        },
        "active_symbols_skipped": len(active_symbols),
        "duplicates_removed": len(raw_candidates) - len(candidates),
        "candidates_produced": len(candidates),
        "candidates": candidates,
    }

    with open(CANDIDATES_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"BB Paper Dispatcher: {len(candidates)} candidates written to {CANDIDATES_PATH}")
    return result


def main():
    dispatch_paper_candidates()
    return 0


if __name__ == "__main__":
    sys.exit(main())
