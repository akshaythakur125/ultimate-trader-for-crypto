"""Daily trade candidate report -- decision-support only.

Scans all allowed configs, computes setup levels, applies RR/direction
gates, ranks candidates, and selects the best. Multi-candidate doctor mode.

Usage:
    python -m production_replay.today_trade_plan
"""

import json, os, sys
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.evidence_ledger import read_latest_entry
from production_replay.setup_compute import load_candles, compute_atr, compute_setup_levels, infer_direction

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
TXT_REPORT = os.path.join(RESULTS_DIR, "today_trade_plan.txt")
JSON_REPORT = os.path.join(RESULTS_DIR, "today_trade_plan.json")
ACCELERATED_PATH = os.path.join(RESULTS_DIR, "accelerated_evidence_report.json")

MIN_TRADES = 100
MIN_DAYS = 30

CONFIG_SOURCE = "unknown"

# Hard doctor display universe fallback — guaranteed to produce BTCUSDT rows.
# This is display/scanner only. NEVER enables live or paper trading.
DOCTOR_DISPLAY_UNIVERSE = [
    {"symbol": "BTCUSDT", "timeframe": "15m"},
    {"symbol": "BTCUSDT", "timeframe": "30m"},
    {"symbol": "SOLUSDT", "timeframe": "15m", "optional": True},
]


def _read_accelerated() -> dict | None:
    if not os.path.exists(ACCELERATED_PATH):
        return None
    with open(ACCELERATED_PATH) as f:
        return json.load(f)


def _get_accelerated_for(acc: dict | None, symbol: str, tf: str) -> dict | None:
    if not acc:
        return None
    for c in acc.get("candidates", []):
        if c.get("symbol") == symbol and c.get("timeframe") == tf:
            return c
    return None


def grade_setup(trades: int, ev: float, pf: float, dd: float, direction: str, rr_1: float | None = None) -> str:
    if direction == "UNKNOWN" or trades == 0:
        return "C"
    if rr_1 is not None and rr_1 < 1.0:
        return "C"
    ev_ok = ev > 0
    pf_ok = pf >= 1.5
    dd_ok = dd < 12.0
    if ev_ok and pf_ok and dd_ok:
        return "B"
    return "C"


def check_rr_gate(rr_2: float | None) -> tuple[bool, str]:
    if rr_2 is None:
        return False, "RR cannot be calculated"
    if rr_2 < 1.5:
        return False, "RR too poor"
    return True, "RR OK"


def scan_candidate(symbol: str, tf: str, acc: dict | None, trades_global: int, days_global: int) -> dict:
    """Scan one config and return a dict with all computed fields."""
    acc_data = _get_accelerated_for(acc, symbol, tf)
    ev = acc_data.get("ev", 0) if acc_data else 0
    pf = acc_data.get("pf", 0) if acc_data else 0
    dd = acc_data.get("max_dd", 0) if acc_data else 0
    trades = acc_data.get("trades", 0) if acc_data else 0

    candles = load_candles(symbol, tf)
    direction = "UNKNOWN"
    levels = {"direction": "UNKNOWN", "latest_close": None,
              "entry_zone": None, "stop": None,
              "target_1": None, "target_2": None, "rr_1": None, "rr_2": None}
    if len(candles) >= 5:
        direction = infer_direction(candles)
    if len(candles) >= 20 and direction != "UNKNOWN":
        atr = compute_atr(candles)
        levels = compute_setup_levels(candles, atr, direction)
    elif candles:
        levels = {"direction": direction, "latest_close": candles[-1]["close"] if candles else None,
                  "entry_zone": None, "stop": None,
                  "target_1": None, "target_2": None, "rr_1": None, "rr_2": None}

    direction = levels["direction"]
    rr_1 = levels.get("rr_1")
    rr_2 = levels.get("rr_2")
    rr_pass, rr_reason = check_rr_gate(rr_2)
    setup_grade = grade_setup(trades, ev, pf, dd, direction, rr_1)

    # Candidate verdict
    if direction == "UNKNOWN":
        verdict = "REJECTED"
        reason = "direction UNKNOWN"
    elif not rr_pass:
        verdict = "REJECTED"
        reason = rr_reason
    else:
        verdict = "CANDIDATE"
        reason = "OK"

    return {
        "label": f"{symbol} {tf}",
        "symbol": symbol,
        "timeframe": tf,
        "direction": direction,
        "setup_quality": setup_grade,
        "entry_zone": levels.get("entry_zone"),
        "stop": levels.get("stop"),
        "target_1": levels.get("target_1"),
        "target_2": levels.get("target_2"),
        "rr_1": rr_1,
        "rr_2": rr_2,
        "rr_gate": "PASS" if rr_pass else "FAIL",
        "rr_gate_reason": rr_reason,
        "ev": ev,
        "pf": pf,
        "dd": dd,
        "trades": trades,
        "verdict": verdict,
        "verdict_reason": reason,
    }


def _load_display_configs() -> list[tuple[str, str, bool]]:
    """Load configs for display scanning from DOCTOR_DISPLAY_UNIVERSE.

    Always includes BTCUSDT 15m and BTCUSDT 30m.
    SOLUSDT 15m is optional — included only if candle data exists.
    This is display/scanner only. NEVER enables live or paper trading.

    Returns list of (symbol, timeframe, is_allowed) triples.
    """
    global CONFIG_SOURCE
    CONFIG_SOURCE = "doctor_display_universe"

    pairs = []
    for entry in DOCTOR_DISPLAY_UNIVERSE:
        sym, tf = entry["symbol"], entry["timeframe"]
        if entry.get("optional"):
            data_path = os.path.join(os.path.dirname(__file__), "..", "data", "historical", f"{sym}_{tf}.csv")
            if os.path.exists(data_path):
                pairs.append((sym, tf, False))
        else:
            pairs.append((sym, tf, True))

    return pairs


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    entry = read_latest_entry()
    acc = _read_accelerated()

    # Always locked — regardless of config parsing
    live_disabled = True
    paper_disabled = True

    if entry:
        trades = entry.get("total_trades", 0)
        days = entry.get("calendar_days", 0)
        kill = entry.get("kill_status") == "KILL"
        safety_ok = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED"
        launch_ok = entry.get("launch_check_verdict") == "PASS"
    else:
        trades = 0; days = 0
        kill = False; safety_ok = True; launch_ok = True

    # Scan all candidates (SKIPPED for non-allowed if data not available)
    config_items = _load_display_configs()
    candidates = []
    for sym, tf, is_allowed in config_items:
        if not is_allowed:
            # SOLUSDT 15m is a bonus scan — include as SKIPPED if no candle data
            candle_path = os.path.join(os.path.dirname(__file__), "..", "data", "historical", f"{sym}_{tf}.csv")
            if not os.path.exists(candle_path):
                candidates.append({
                    "label": f"{sym} {tf}", "symbol": sym, "timeframe": tf,
                    "direction": "SKIPPED", "setup_quality": "N/A",
                    "entry_zone": None, "stop": None,
                    "target_1": None, "target_2": None, "rr_1": None, "rr_2": None,
                    "rr_gate": "SKIPPED", "rr_gate_reason": "no data file",
                    "ev": 0, "pf": 0, "dd": 0, "trades": 0,
                    "verdict": "SKIPPED", "verdict_reason": "no data file",
                })
                continue
        candidates.append(scan_candidate(sym, tf, acc, trades, days))

    # Select best passing candidate
    passing = [c for c in candidates if c["verdict"] == "CANDIDATE"]
    if passing:
        passing.sort(key=lambda c: (c.get("rr_2") or 0), reverse=True)
        selected = passing[0]
    else:
        selected = None

    # Decision rules
    decision = "MANUAL_REVIEW_ONLY"
    reasons = []

    if not safety_ok:
        decision = "WAIT"
        reasons.append("safety lock failed")
    if not launch_ok:
        decision = "WAIT"
        reasons.append("launch check failed")
    if not live_disabled:
        decision = "WAIT"
        reasons.append("live trading not disabled")
    if not paper_disabled:
        decision = "WAIT"
        reasons.append("paper trading not disabled")
    if kill:
        decision = "WAIT"
        reasons.append("kill switch triggered")
    if selected is None:
        decision = "WAIT"
        reasons.append("no candidate passes RR gate")
    if trades < MIN_TRADES or days < MIN_DAYS:
        if decision not in ("WAIT",):
            decision = "MANUAL_REVIEW_ONLY"
        reasons.append(f"evidence incomplete ({trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days)")
    if decision == "MANUAL_REVIEW_ONLY" and not reasons:
        reasons.append("evidence gates not met -- trade at your own risk")

    reason_str = "; ".join(reasons) if reasons else "all checks pass"

    # Build candidate table for report
    cand_rows = []
    for c in candidates:
        rr1s = f"1:{c['rr_1']:.2f}" if c["rr_1"] is not None else "N/A"
        rr2s = f"1:{c['rr_2']:.2f}" if c["rr_2"] is not None else "N/A"
        reason = c.get("verdict_reason", "")
        cand_rows.append({
            "label": c["label"],
            "direction": c["direction"],
            "rr_t1": rr1s,
            "rr_t2": rr2s,
            "quality": c["setup_quality"],
            "rr_gate": c["rr_gate"],
            "verdict": c["verdict"],
            "reason": reason,
        })

    report: dict[str, Any] = {
        "mode": "today_trade_plan",
        "research_only": True,
        "timestamp": datetime.now().isoformat(),
        "config_source": CONFIG_SOURCE,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "system_safe": safety_ok and launch_ok,
        "live_disabled": live_disabled,
        "paper_disabled": paper_disabled,
        "trade_decision": decision,
        "candidates": cand_rows,
        "selected_candidate": selected["label"] if selected else None,
        "selected_levels": {
            "direction": selected["direction"] if selected else "UNKNOWN",
            "entry_zone": selected["entry_zone"] if selected else None,
            "stop": selected["stop"] if selected else None,
            "target_1": selected["target_1"] if selected else None,
            "target_2": selected["target_2"] if selected else None,
            "rr_1": selected["rr_1"] if selected else None,
            "rr_2": selected["rr_2"] if selected else None,
        } if selected else {},
        "evidence": {
            "trades_collected": trades,
            "calendar_days_collected": days,
            "kill_switch": "KILL" if kill else "OK",
        },
        "reason": reason_str,
        "disclaimer": "This system is not approved for live trading. Manual trading is at user's own risk.",
    }

    with open(JSON_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    # Build text output
    lines = [
        "=" * 60,
        "  TODAY TRADE PLAN -- Decision Support Only",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  SYSTEM SAFE:    {'YES' if report['system_safe'] else 'NO'}",
        f"  LIVE DISABLED:  {'YES' if live_disabled else 'NO'}",
        f"  PAPER DISABLED: {'YES' if paper_disabled else 'NO'}",
        "",
        f"  TRADE DECISION: {decision}",
        "",
        "  Candidate Scan:",
        "  {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            "Config", "Direction", "RR T1", "RR T2", "Quality", "RR Gate", "Verdict", "Reason"),
        "  " + "-" * 88,
    ]
    for c in cand_rows:
        lines.append("  {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            c["label"], c["direction"], c["rr_t1"], c["rr_t2"],
            c["quality"], c["rr_gate"], c["verdict"], c["reason"][:20]))
    lines.append("  " + "-" * 88)

    if selected:
        sel = selected
        lines += [
            "",
            f"  Selected: {sel['label']} ({sel['direction']})",
            f"    Entry zone:  {sel['entry_zone']:.2f}" if sel["entry_zone"] is not None else "    Entry zone:  N/A",
            f"    Stop:        {sel['stop']:.2f}" if sel["stop"] is not None else "    Stop:        N/A",
            f"    Target 1:    {sel['target_1']:.2f}  (RR 1:{sel['rr_1']:.2f})" if sel["target_1"] is not None else "    Target 1:    N/A",
            f"    Target 2:    {sel['target_2']:.2f}  (RR 1:{sel['rr_2']:.2f})" if sel["target_2"] is not None else "    Target 2:    N/A",
        ]
    else:
        lines += ["", "  Selected: NONE (no candidate passes all gates)"]

    lines += [
        "",
        "  Evidence Status:",
        f"    Trades:  {trades} / {MIN_TRADES}",
        f"    Days:    {days} / {MIN_DAYS}",
        f"    Kill:    {'KILL' if kill else 'OK'}",
        "",
        f"  Reason: {reason_str}",
        "",
        "  WARNING:",
        "  " + report["disclaimer"],
        "",
        "=" * 60,
    ]

    with open(TXT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\n[JSON] {JSON_REPORT}")
    print(f"[TXT]  {TXT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
