"""BingX shadow execution bridge — converts Dux candidates to simulated order intents.

SHADOW_ONLY mode. Never places real orders.
Reads dux_pattern_report.json, doctor_daily_packet.json, manual_risk_plan.json.
"""

import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_universe import is_bingx_listed, load_universe, is_crypto_usdt_perp

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "bingx_order_intent.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "bingx_order_intent.json")
SHADOW_LEDGER = os.path.join(STATE_DIR, "bingx_shadow_orders.jsonl")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _shadow_order_intent(
    candidate: dict,
    symbol: str,
    side: str,
    entry: float,
    stop_loss: float,
    final_target: float,
    rr_final: float,
    source_pattern: str,
    pattern_id: str,
    pattern_name: str,
    verdict: str,
    position_size: float = 0.0,
    risk_usdt: float = 0.0,
    max_loss_usdt: float = 0.0,
    reason: str = "",
) -> dict:
    return {
        "timestamp": datetime.now().isoformat(),
        "mode": "SHADOW_ONLY",
        "real_order": False,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "stop_loss": stop_loss,
        "target_1": round(entry + (entry - stop_loss) * 1.0 if side == "LONG" else entry - (stop_loss - entry) * 1.0, 2),
        "final_target": final_target,
        "rr_final": rr_final,
        "position_size": position_size,
        "risk_usdt": risk_usdt,
        "max_loss_usdt": max_loss_usdt,
        "source_pattern": source_pattern,
        "pattern_id": pattern_id,
        "pattern_name": pattern_name,
        "verdict": verdict,
        "reason": reason,
    }


def run_shadow_executor() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    alpha = _read_json(os.path.join(RESULTS_DIR, "alpha_intelligence_report.json"))
    psych = _read_json(os.path.join(RESULTS_DIR, "psychology_alpha_report.json"))
    near_miss = _read_json(os.path.join(RESULTS_DIR, "near_miss_report.json"))
    doctor = _read_json(os.path.join(RESULTS_DIR, "doctor_daily_packet.json"))
    risk_plan = _read_json(os.path.join(RESULTS_DIR, "manual_risk_plan.json"))

    reasons = []
    decision = "DO_NOT_EXECUTE"
    show_reasons = []
    dux_decision = "N/A"
    # Always defined so the report block below never hits UnboundLocalError on
    # a no-trade cycle (it is overwritten when an order intent is built).
    risk_usdt = 0.0

    # Shared risk/kill params
    risk_params = risk_plan.get("risk_parameters", {})
    max_risk_per_trade = risk_params.get("max_risk_per_trade_usdt", 1.0)
    max_daily_loss = risk_params.get("max_daily_loss_usdt", 2.0)
    max_weekly_loss = risk_params.get("max_weekly_loss_usdt", 5.0)
    evidence = risk_plan.get("evidence", {})
    kill_switch = evidence.get("kill_switch", "OK")

    # Phase 50: Check for trigger bridge candidate first
    arbiter = _read_json(os.path.join(RESULTS_DIR, "candidate_arbiter_report.json"))
    arbiter_best = arbiter.get("best_candidate") if arbiter else None
    trigger_watcher = _read_json(os.path.join(RESULTS_DIR, "trigger_watcher_report.json"))

    # Determine if we have a trigger bridge candidate
    bridge_candidate = None
    bridge_active = False
    if arbiter_best:
        csrc = arbiter_best.get("candidate_source", "near_miss")
        tstat = arbiter_best.get("trigger_status", "")
        if csrc == "trigger_watcher" and tstat == "TRIGGER_CONFIRMED":
            rr_ok = float(arbiter_best.get("rr", 0)) >= 4.0
            thesis_ok = float(arbiter_best.get("thesis_score", 0)) >= 75
            sym_ok = bool(arbiter_best.get("symbol", ""))
            dir_ok = arbiter_best.get("direction", "") in ("LONG", "SHORT")
            entry_ok = float(arbiter_best.get("entry", 0)) > 0
            stop_ok = float(arbiter_best.get("stop", 0)) > 0
            target_ok = float(arbiter_best.get("target", 0)) > 0
            crypto_ok = is_crypto_usdt_perp(arbiter_best.get("symbol", ""))
            bingx_ok = is_bingx_listed(arbiter_best.get("symbol", ""), load_universe()["contracts"])
            if rr_ok and thesis_ok and sym_ok and dir_ok and entry_ok and stop_ok and target_ok and crypto_ok and bingx_ok:
                bridge_active = True
                bridge_candidate = arbiter_best

    # ── TRIGGER BRIDGE PATH (fully self-contained) ──
    if bridge_active:
        symbol = bridge_candidate.get("symbol", "")
        direction = bridge_candidate.get("direction", "")
        entry = float(bridge_candidate.get("entry", 0))
        stop = float(bridge_candidate.get("stop", 0))
        target = float(bridge_candidate.get("target", 0))
        rr_final = float(bridge_candidate.get("rr", 0))
        candidate = {
            "symbol": symbol,
            "timeframe": bridge_candidate.get("timeframe", ""),
            "direction": direction,
            "rr_2": rr_final,
            "entry": entry,
            "stop": stop,
            "target_2": target,
            "psychology_score": bridge_candidate.get("psychology_score", 0),
            "thesis_score": bridge_candidate.get("thesis_score", 0),
            "raw_anomaly_score": bridge_candidate.get("raw_anomaly_score", 0),
            "pattern_name": bridge_candidate.get("thesis_type", "TRIGGER_BRIDGE"),
            "pattern_id": "trigger_bridge_%s_%s" % (symbol, bridge_candidate.get("timeframe", "")),
            "verdict": bridge_candidate.get("verdict", "SHADOW_ELIGIBLE"),
            "candidate_source": "trigger_watcher",
            "trigger_status": "TRIGGER_CONFIRMED",
        }
        reasons.append("trigger bridge candidate accepted; bypassing Dux/alpha/psych gates")

        # Bridge-specific safety gates
        bridge_ok = True
        bridge_gate_reasons = []

        if not doctor.get("system_safe", False):
            bridge_gate_reasons.append("system not safe")
            bridge_ok = False

        if not doctor.get("live_disabled", False):
            bridge_gate_reasons.append("live trading not disabled")
            bridge_ok = False

        if not doctor.get("paper_disabled", False):
            bridge_gate_reasons.append("paper trading not disabled")
            bridge_ok = False

        risk_per_trade = abs(entry - stop)
        if risk_per_trade > max_risk_per_trade:
            bridge_gate_reasons.append("risk %.2f USDT > max %.2f USDT per trade" % (risk_per_trade, max_risk_per_trade))
            bridge_ok = False

        if kill_switch == "STOP":
            bridge_gate_reasons.append("kill switch engaged")
            bridge_ok = False

        pos_mon = _read_json(os.path.join(RESULTS_DIR, "position_monitor_status.json"))
        if pos_mon and pos_mon.get("position_found", False):
            open_positions = float(pos_mon.get("open_position_count", 1))
            if open_positions >= 1:
                bridge_gate_reasons.append("open position exists (%s)" % pos_mon.get("symbol", "?"))
                bridge_ok = False

        if bridge_ok:
            decision = "SHADOW_READY"
            risk_usdt = abs(entry - stop)
            position_size = risk_usdt / max(risk_usdt, 1e-10)
            order_intent = _shadow_order_intent(
                candidate=candidate,
                symbol=symbol,
                side=direction,
                entry=entry,
                stop_loss=stop,
                final_target=target,
                rr_final=rr_final,
                source_pattern=candidate.get("pattern_name", ""),
                pattern_id=candidate.get("pattern_id", ""),
                pattern_name=candidate.get("pattern_name", ""),
                verdict=candidate.get("verdict", ""),
                position_size=round(position_size, 4),
                risk_usdt=round(risk_usdt, 2),
                max_loss_usdt=round(max_risk_per_trade, 2),
                reason="all gates passed",
            )
            order_intent["source"] = "trigger_bridge"
            order_intent["candidate_source"] = candidate.get("candidate_source", "near_miss")
            order_intent["trigger_status"] = candidate.get("trigger_status", "N/A")
            order_intent["thesis_score"] = candidate.get("thesis_score", 0)
            _append_to_ledger(order_intent)
        else:
            order_intent = None
            show_reasons = bridge_gate_reasons

    # ── OLD DUX PATH (fallback) ──
    else:
        gate_reasons = []
        order_intent = None

        # Extract alpha score
        alpha_candidate = alpha.get("best_candidate") if alpha else None
        alpha_score = alpha_candidate["alpha_score"] if alpha_candidate else None

        # Extract psychology score
        psych_candidate = psych.get("best_candidate") if psych else None
        psychology_score = psych_candidate["psychology_score"] if psych_candidate else None

        # Gate 0: alpha_score >= 70
        if alpha_score is None or alpha_score < 70:
            gate_reasons.append("alpha score %s < 70" % alpha_score)

        # Gate 0b: psychology_score >= 70
        if psychology_score is None or psychology_score < 70:
            gate_reasons.append("psychology score %s < 70" % psychology_score)

        # Gate 4: Dux decision
        dux_decision = (dux.get("dux_pattern_engine") or dux).get("final_decision", dux.get("final_decision", "DO_NOT_TRADE"))
        if dux.get("mode") == "dux_pattern_engine":
            dux_decision = dux.get("final_decision", "DO_NOT_TRADE")
        elif "dux_pattern_engine" in doctor:
            dux_decision = doctor["dux_pattern_engine"].get("final_decision", "DO_NOT_TRADE")

        if dux_decision not in ("WATCH", "MANUAL_REVIEW_ONLY"):
            gate_reasons.append("Dux decision is %s, not WATCH or MANUAL_REVIEW_ONLY" % dux_decision)

        # Gate 5: candidate exists
        candidate = None
        if dux.get("mode") == "dux_pattern_engine":
            candidate = dux.get("best_candidate")
        else:
            dux_section = doctor.get("dux_pattern_engine", {})
            candidate = dux_section.get("best_candidate")

        if not candidate:
            gate_reasons.append("no valid Dux candidate")

        # Gate 6: crypto-only filter
        symbol = (candidate or {}).get("symbol", "")
        if symbol and not is_crypto_usdt_perp(symbol):
            gate_reasons.append("%s is not a crypto USDT perpetual (non-crypto synthetic)" % symbol)

        # Gate 6b: candidate arbiter check
        if arbiter and not arbiter.get("has_shadow_eligible_candidates", False):
            gate_reasons.append("candidate arbiter has no shadow-eligible candidates")

        # Gate 6c: trigger watcher check
        if trigger_watcher and arbiter_best:
            tw_key = "%s|%s|%s|%s" % (arbiter_best.get("symbol", ""), arbiter_best.get("timeframe", ""), arbiter_best.get("direction", ""), arbiter_best.get("thesis_type", ""))
            for tc in trigger_watcher.get("candidates", []):
                tck = "%s|%s|%s|%s" % (tc.get("symbol", ""), tc.get("timeframe", ""), tc.get("direction", ""), tc.get("thesis_type", ""))
                if tck == tw_key and tc.get("trigger_status") in ("INVALIDATED", "EXPIRED"):
                    gate_reasons.append("trigger watcher: %s for this candidate" % tc.get("trigger_status"))

        # If arbiter best exists, use its candidate data instead
        if arbiter_best and not any("trigger watcher" in r for r in gate_reasons):
            candidate = {
                "symbol": arbiter_best.get("symbol", ""),
                "timeframe": arbiter_best.get("timeframe", ""),
                "direction": arbiter_best.get("direction", ""),
                "rr_2": arbiter_best.get("rr", 0),
                "entry": arbiter_best.get("entry", 0),
                "stop": arbiter_best.get("stop", 0),
                "target_2": arbiter_best.get("target", 0),
                "psychology_score": arbiter_best.get("psychology_score", 0),
                "thesis_score": arbiter_best.get("thesis_score", 0),
                "raw_anomaly_score": arbiter_best.get("raw_anomaly_score", 0),
                "pattern_name": arbiter_best.get("thesis_type", "ARBITER_PASS"),
                "pattern_id": "arbiter_%s_%s" % (arbiter_best.get("symbol", ""), arbiter_best.get("timeframe", "")),
                "verdict": "SHADOW_ELIGIBLE",
            }

        # Gate 6c: symbol BingX-listed
        if symbol:
            universe = load_universe()["contracts"]
            if not is_bingx_listed(symbol, universe):
                gate_reasons.append("%s not BingX-listed" % symbol)
        else:
            gate_reasons.append("no symbol from candidate")

        # Gate 7: direction
        direction = (candidate or {}).get("direction", "")
        if direction not in ("LONG", "SHORT"):
            gate_reasons.append("invalid direction: %s" % direction)

        # Gate 8: RR final >= 4.0
        rr_final = (candidate or {}).get("rr_2") or 0
        if rr_final < 4.0:
            gate_reasons.append("RR %s < 4.0" % rr_final)

        # Gate 9: entry valid
        entry = (candidate or {}).get("entry") or 0
        if entry <= 0:
            gate_reasons.append("invalid entry")

        # Gate 10: stop valid
        stop = (candidate or {}).get("stop") or 0
        if stop <= 0 or stop == entry:
            gate_reasons.append("invalid stop")

        # Gate 11: target valid
        target = (candidate or {}).get("target_2") or 0
        if target <= 0:
            gate_reasons.append("invalid target")

        # Common safety gates (Dux path only)
        if not doctor.get("system_safe", False):
            gate_reasons.append("system not safe")

        if not doctor.get("live_disabled", False):
            gate_reasons.append("live trading not disabled")

        if not doctor.get("paper_disabled", False):
            gate_reasons.append("paper trading not disabled")

        risk_per_trade = abs(entry - stop)
        if risk_per_trade > max_risk_per_trade:
            gate_reasons.append("risk %.2f USDT > max %.2f USDT per trade" % (risk_per_trade, max_risk_per_trade))

        if kill_switch == "STOP":
            gate_reasons.append("kill switch engaged")

        pos_mon = _read_json(os.path.join(RESULTS_DIR, "position_monitor_status.json"))
        if pos_mon and pos_mon.get("position_found", False):
            open_positions = float(pos_mon.get("open_position_count", 1))
            if open_positions >= 1:
                gate_reasons.append("open position exists (%s)" % pos_mon.get("symbol", "?"))

        if not gate_reasons:
            decision = "SHADOW_READY"
            risk_usdt = abs(entry - stop)
            position_size = risk_usdt / max(risk_usdt, 1e-10)
            order_intent = _shadow_order_intent(
                candidate=candidate,
                symbol=symbol,
                side=direction,
                entry=entry,
                stop_loss=stop,
                final_target=target,
                rr_final=rr_final,
                source_pattern=candidate.get("pattern_name", ""),
                pattern_id=candidate.get("pattern_id", ""),
                pattern_name=candidate.get("pattern_name", ""),
                verdict=candidate.get("verdict", ""),
                position_size=round(position_size, 4),
                risk_usdt=round(risk_usdt, 2),
                max_loss_usdt=round(max_risk_per_trade, 2),
                reason="all gates passed",
            )
            order_intent["source"] = "dux"
            order_intent["candidate_source"] = candidate.get("candidate_source", "near_miss") if candidate else "near_miss"
            order_intent["trigger_status"] = candidate.get("trigger_status", "N/A") if candidate else "N/A"
            order_intent["thesis_score"] = candidate.get("thesis_score", 0) if candidate else 0
            _append_to_ledger(order_intent)

        show_reasons = gate_reasons

    report = {
        "mode": "bingx_shadow_executor",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "execution_mode": "SHADOW_ONLY",
        "real_order": False,
        "timestamp": datetime.now().isoformat(),
        "inputs": {
            "candidate_arbiter": "candidate_arbiter_report.json",
            "trigger_watcher": "trigger_watcher_report.json",
            "dux_pattern_report": "dux_pattern_report.json",
            "doctor_daily_packet": "doctor_daily_packet.json",
            "manual_risk_plan": "manual_risk_plan.json",
        },
        "candidate_from_arbiter": arbiter_best is not None,
        "trigger_bridge_active": bridge_active,
        "dux_decision": dux_decision if not bridge_active else "TRIGGER_BRIDGE_BYPASS",
        "system_safe": doctor.get("system_safe", False),
        "live_disabled": doctor.get("live_disabled", False),
        "paper_disabled": doctor.get("paper_disabled", False),
        "crypto_filter_pass": bool(symbol) and is_crypto_usdt_perp(symbol) if symbol else False,
        "candidate_exists": candidate is not None,
        "candidate_source": candidate.get("candidate_source", "near_miss") if candidate else "near_miss",
        "symbol_bingx_listed": bool(symbol) and is_bingx_listed(symbol, load_universe()["contracts"]) if symbol else False,
        "direction": direction,
        "rr_final": rr_final,
        "entry": entry,
        "stop": stop,
        "target": target,
        "kill_switch": kill_switch,
        "risk_per_trade_usdt": risk_usdt,
        "max_risk_per_trade_usdt": max_risk_per_trade,
        "max_daily_loss_usdt": max_daily_loss,
        "max_weekly_loss_usdt": max_weekly_loss,
        "shadow_order_intent": order_intent,
        "decision": decision,
        "reasons": show_reasons if show_reasons else (["all gates passed"] if not reasons and decision == "SHADOW_READY" else reasons),
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, order_intent, decision, show_reasons if show_reasons else reasons)
    return report


def _append_to_ledger(intent: dict):
    with open(SHADOW_LEDGER, "a") as f:
        f.write(json.dumps(intent) + "\n")


def _write_text_report(report: dict, intent: dict | None, decision: str, reasons: list[str]):
    lines = [
        "=" * 60,
        "  BINGX SHADOW EXECUTION BRIDGE",
        "  %s" % datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "=" * 60,
        "",
        "  System Safe:           %s" % ('YES' if report['system_safe'] else 'NO'),
        "  Live Disabled:         %s" % ('YES' if report['live_disabled'] else 'NO'),
        "  Paper Disabled:        %s" % ('YES' if report['paper_disabled'] else 'NO'),
        "  Trigger Bridge:        %s" % ('ACTIVE' if report.get('trigger_bridge_active') else 'INACTIVE'),
        "  Crypto Filter:         %s" % ('PASS' if report.get('crypto_filter_pass') else 'FAIL'),
        "  Dux Decision:          %s" % report['dux_decision'],
        "  Candidate Exists:      %s" % ('YES' if report['candidate_exists'] else 'NO'),
        "  Candidate from Arbiter:%s" % ('YES' if report.get('candidate_from_arbiter') else 'NO'),
        "  Symbol BingX-Listed:   %s" % ('YES' if report['symbol_bingx_listed'] else 'NO'),
        "  Candidate Source:      %s" % report.get('candidate_source', 'near_miss'),
        "  Direction:             %s" % (report['direction'] or 'N/A'),
        "  RR Final:              %s" % report['rr_final'],
        "  Risk per Trade (USDT): %.2f" % report['risk_per_trade_usdt'],
        "  Kill Switch:           %s" % report['kill_switch'],
        "",
        "  EXECUTION MODE: SHADOW_ONLY",
        "  REAL ORDER:     FALSE",
        "",
    ]

    if intent:
        lines += [
            "  SHADOW ORDER INTENT GENERATED:",
            "    Source:    %s" % intent.get('source', 'dux'),
            "    Symbol:    %s" % intent['symbol'],
            "    Side:      %s" % intent['side'],
            "    Entry:     %s" % intent['entry'],
            "    Stop:      %s" % intent['stop_loss'],
            "    Target 1:  %s" % intent['target_1'],
            "    Final Tgt: %s" % intent['final_target'],
            "    RR Final:  1:%s" % intent['rr_final'],
            "    Thesis:    %s" % intent.get('thesis_score', 'N/A'),
            "    Size:      %s" % intent['position_size'],
            "    Risk:      %s USDT" % intent['risk_usdt'],
            "    Pattern:   %s" % intent['pattern_name'],
            "    Verdict:   %s" % intent['verdict'],
            "",
        ]
    else:
        lines += ["  SHADOW ORDER INTENT: NOT GENERATED", ""]

    lines += [
        "  DECISION: %s" % decision,
        "",
    ]
    if reasons:
        for r in reasons:
            lines.append("    - %s" % r)
        lines.append("")

    lines += [
        "  WARNING: Shadow execution only. No real orders placed.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\n[JSON] %s" % JSON_PATH)
    print("[TXT]  %s" % TXT_PATH)
    if intent:
        print("[LEDGER] %s" % SHADOW_LEDGER)


def main():
    report = run_shadow_executor()
    return 0


if __name__ == "__main__":
    sys.exit(main())
