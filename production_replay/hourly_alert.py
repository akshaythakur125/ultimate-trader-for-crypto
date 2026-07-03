"""Hourly alert and final status system.

Reads doctor packet, Dux report, shadow/live execution outputs
and produces a clean one-page status with a final action.

Usage:
    python -m production_replay.hourly_alert
"""

import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import load_credentials
from production_replay.final_decision_resolver import resolve_final_action

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "hourly_status.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "hourly_status.json")
ALERT_LEDGER = os.path.join(STATE_DIR, "hourly_alerts.jsonl")
KILL_SWITCH_FILE = os.path.join(STATE_DIR, "KILL_SWITCH_ON")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _kill_switch_active() -> bool:
    return os.path.exists(KILL_SWITCH_FILE)


def _determine_final_action(
    dux_decision: str,
    rr_gate_pass: int,
    alpha_score: int,
    alpha_decision: str,
    shadow_decision: str,
    live_decision: str,
    live_armed: bool,
    execution_mode: str,
    position_open: bool = False,
    emergency: bool = False,
    executable_count: int = 0,
    watchlist_count: int = 0,
    near_miss_count: int = 0,
    bridge_shadow_ready: bool = False,
    preflight_pass: bool = False,
    live_blocked_by_env: bool = False,
) -> tuple[str, str]:
    # Rule 0: trigger bridge + preflight pass + only env blocking (Phase 55)
    if bridge_shadow_ready and preflight_pass and live_blocked_by_env:
        return "LIVE_REVIEW_READY", "Trigger bridge preflight passed; requires manual review for live"

    # Rule 0b: trigger bridge shadow ready (Phase 51)
    if bridge_shadow_ready:
        return "SHADOW_READY", "Trigger bridge candidate ready for shadow execution"

    if emergency:
        return "EMERGENCY_EXIT_REQUIRED", "Emergency situation detected"
    if position_open:
        return "POSITION_OPEN_MONITORING", "Live position open; continuous monitoring active"

    # Rule 1: executable + shadow ready
    if executable_count > 0 and shadow_decision == "SHADOW_READY" and live_armed and execution_mode == "live_micro":
        return "SHADOW_READY", f"{executable_count} executable candidate(s); shadow ready"
    if executable_count > 0 and shadow_decision == "SHADOW_READY":
        if not live_armed or execution_mode != "live_micro":
            return "LIVE_BLOCKED", f"{executable_count} executable candidate(s) but live execution blocked (read_only mode)"

    # Rule 2: watchlist or near-miss exists -> REVIEW_NOW
    if watchlist_count > 0 or near_miss_count > 0:
        reasons = []
        if watchlist_count > 0:
            reasons.append(f"{watchlist_count} watchlist-ready")
        if near_miss_count > 0:
            reasons.append(f"{near_miss_count} near-miss")
        return "REVIEW_NOW", f"Diagnostic candidates found: {', '.join(reasons)}; manual review recommended"

    # Rule 3: shadow ready fallback
    if shadow_decision == "SHADOW_READY":
        return "SHADOW_READY", "Shadow order intent ready for execution"

    # Fallback
    return "DO_NOTHING", "No actionable signal"


def run_hourly_alert() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    # Run paper rotation engine for fresh data (Phase 63)
    try:
        subprocess.run(
            [sys.executable, "-m", "production_replay.paper_rotation_engine"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass
    # Run paper execution ledger for fresh data (Phase 59)
    import subprocess
    try:
        subprocess.run(
            [sys.executable, "-m", "production_replay.paper_execution_ledger"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass
    # Run paper outcome validator for fresh data (Phase 60)
    try:
        subprocess.run(
            [sys.executable, "-m", "production_replay.paper_outcome_validator"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass
    # Run candidate rotation report for fresh data (Phase 61)
    try:
        subprocess.run(
            [sys.executable, "-m", "production_replay.candidate_rotation_report"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass
    # Run paper candidate watchlist for fresh data (Phase 62)
    try:
        subprocess.run(
            [sys.executable, "-m", "production_replay.paper_candidate_watchlist"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass
    # Run strategy evidence lock for fresh data (Phase 64)
    try:
        subprocess.run(
            [sys.executable, "-m", "production_replay.strategy_evidence_lock"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass

    doctor = _read_json(os.path.join(RESULTS_DIR, "doctor_daily_packet.json"))
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    alpha = _read_json(os.path.join(RESULTS_DIR, "alpha_intelligence_report.json"))
    psych = _read_json(os.path.join(RESULTS_DIR, "psychology_alpha_report.json"))
    memory = _read_json(os.path.join(RESULTS_DIR, "psychology_memory_report.json"))
    near_miss = _read_json(os.path.join(RESULTS_DIR, "near_miss_report.json"))
    trigger_watcher = _read_json(os.path.join(RESULTS_DIR, "trigger_watcher_report.json"))
    trigger_active = _read_json(os.path.join(STATE_DIR, "trigger_watchlist_active.json"))
    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    live = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))
    preflight = _read_json(os.path.join(RESULTS_DIR, "bingx_live_preflight.json"))
    paper = _read_json(os.path.join(RESULTS_DIR, "paper_execution_status.json"))
    paper_outcome = _read_json(os.path.join(RESULTS_DIR, "paper_outcome_report.json"))
    rotation = _read_json(os.path.join(RESULTS_DIR, "candidate_rotation_report.json"))
    paper_rotation = _read_json(os.path.join(RESULTS_DIR, "paper_rotation_report.json"))
    watchlist = _read_json(os.path.join(RESULTS_DIR, "paper_candidate_watchlist.json"))
    evidence = _read_json(os.path.join(RESULTS_DIR, "strategy_evidence_report.json"))
    from production_replay.live_one_shot_guard import read_state as _read_one_shot
    one_shot_state = _read_one_shot()
    universe = _read_json(os.path.join(RESULTS_DIR, "bingx_universe.json"))

    ts = datetime.now().isoformat()

    # Crypto-only stats
    crypto_excluded = universe.get("excluded_non_crypto", 0) if universe else 0
    crypto_perps = (universe.get("active_usdt_perps", 0) - crypto_excluded) if universe else 0
    directional_theses = near_miss.get("directional_theses_created", 0) if near_miss else 0
    long_theses = near_miss.get("long_theses", 0) if near_miss else 0
    short_theses = near_miss.get("short_theses", 0) if near_miss else 0

    # Extract fields
    dux_decision = dux.get("final_decision", "DO_NOT_TRADE") if dux else "DO_NOT_TRADE"
    alpha_score = alpha.get("best_candidate", {}).get("alpha_score") if alpha and alpha.get("best_candidate") else None
    alpha_decision = alpha.get("final_decision", "DO_NOT_TRADE") if alpha else "DO_NOT_TRADE"
    psych_score = None
    if psych:
        pc = psych.get("best_candidate")
        psych_score = pc["psychology_score"] if pc else None
    alpha_elite = alpha.get("alpha_elite_candidates", 0) if alpha else 0
    alpha_watch = alpha.get("alpha_watch_candidates", 0) if alpha else 0
    alpha_best = alpha.get("best_candidate") if alpha else None
    dux_scan_size = dux.get("dux_scan_universe_size", dux.get("symbols_scanned", 0))
    st_scanned = dux.get("symbol_timeframes_scanned", 0)
    st_attempted = dux.get("symbol_timeframes_attempted", st_scanned)
    rr_pass = dux.get("rr_gate_pass", 0)
    total_contracts = dux.get("total_raw_contracts", dux.get("total_contracts", 0))
    best = dux.get("best_candidate")
    scan_duration = dux.get("scan_duration_seconds", 0)
    failed_count = dux.get("failed_symbol_count", 0)
    api_err_count = dux.get("api_error_count", 0)
    tier_a = dux.get("tier_a_size", 0)
    tier_b = dux.get("tier_b_size", 0)
    tier_c = dux.get("tier_c_size", 0)

    shadow_decision = shadow.get("decision", "N/A") if shadow else "N/A"
    live_decision = live.get("decision", "N/A") if live else "N/A"
    live_armed = live.get("live_armed", False) if live else False
    execution_mode = live.get("execution_mode", "read_only") if live else "read_only"
    live_blocked_by_env = False
    if live:
        gates = live.get("gates", {})
        env_fail = not gates.get("env_gates", True)
        all_others_pass = (
            gates.get("safety_gates", True)
            and gates.get("strategy_gates", True)
            and gates.get("shadow_gate", True)
            and gates.get("risk_gates", True)
            and gates.get("account_gates", True)
            and gates.get("kill_switch", True)
        )
        if env_fail and all_others_pass:
            live_blocked_by_env = True
    open_positions = live.get("open_position_count", 0) if live else 0
    kill_active = _kill_switch_active()
    preflight_decision = preflight.get("decision", "N/A") if preflight else "N/A"
    preflight_pass = preflight.get("preflight_pass", False) if preflight else False
    creds = load_credentials()
    api_ok = bool(creds.get("api_key") and creds.get("api_secret"))

    position_monitor = _read_json(os.path.join(RESULTS_DIR, "position_monitor_status.json"))
    position_open = position_monitor.get("position_found", False) if position_monitor else False
    emergency = position_monitor.get("emergency_status") == "CRITICAL" if position_monitor else False

    executable_count = near_miss.get("diagnostic_executable_count", 0) if near_miss else 0
    trigger_confirmed_ct = near_miss.get("trigger_confirmed_count", 0) if near_miss else 0
    arbiter_eligible_ct = near_miss.get("arbiter_eligible_count", 0) if near_miss else 0
    watchlist_count = near_miss.get("watchlist_ready_count", 0) if near_miss else 0
    near_miss_rr_ct = near_miss.get("near_miss_rr_count", 0) if near_miss else 0
    near_miss_psych_ct = near_miss.get("near_miss_psychology_count", 0) if near_miss else 0
    near_miss_total = near_miss_rr_ct + near_miss_psych_ct
    top_rejection = near_miss.get("top_rejection_reason", "N/A") if near_miss else "N/A"

    # Trigger watcher stats
    tw_waiting = trigger_watcher.get("waiting_count", 0) if trigger_watcher else 0
    tw_confirmed = trigger_watcher.get("confirmed_count", 0) if trigger_watcher else 0
    tw_invalidated = trigger_watcher.get("invalidated_count", 0) if trigger_watcher else 0
    tw_expired = trigger_watcher.get("expired_count", 0) if trigger_watcher else 0
    tw_best_confirmed = trigger_watcher.get("best_confirmed_candidate") if trigger_watcher else None
    tw_best_waiting = trigger_watcher.get("best_waiting_candidate") if trigger_watcher else None
    tw_active_size = trigger_active.get("total_active", 0) if trigger_active else 0
    tw_candidates_watched = trigger_watcher.get("candidates_watched", 0) if trigger_watcher else 0

    # Candidate arbiter
    arbiter = _read_json(os.path.join(RESULTS_DIR, "candidate_arbiter_report.json"))
    arbiter_shadow_eligible = arbiter.get("shadow_eligible", 0) if arbiter else 0
    arbiter_review_candidate = arbiter.get("review_candidate", 0) if arbiter else 0
    arbiter_do_not_trade = arbiter.get("do_not_trade", 0) if arbiter else 0
    arbiter_best = arbiter.get("best_candidate") if arbiter else None
    arbiter_psych_verdict = arbiter.get("psychology_alpha_best_candidate_verdict") if arbiter else None
    arbiter_shadow_eligible_found = arbiter.get("has_shadow_eligible_candidates", False) if arbiter else False

    # Signal integrity from near_miss
    dedup_removed = near_miss.get("deduplicated_candidates_removed", 0) if near_miss else 0
    exec_downgraded = near_miss.get("executable_downgraded_count", 0) if near_miss else 0
    exec_after = near_miss.get("validated_executable_after", 0) if near_miss else 0

    # Phase 51: check if shadow intent has trigger_bridge source
    bridge_shadow_ready = False
    if shadow and shadow.get("decision") == "SHADOW_READY" and shadow.get("shadow_order_intent"):
        si = shadow["shadow_order_intent"]
        if si.get("source") == "trigger_bridge" or si.get("candidate_source") == "trigger_watcher":
            bridge_shadow_ready = True

    final_action, action_reason = _determine_final_action(
        dux_decision, rr_pass, alpha_score, alpha_decision,
        shadow_decision, live_decision, live_armed, execution_mode,
        position_open=position_open, emergency=emergency,
        executable_count=executable_count,
        watchlist_count=watchlist_count,
        near_miss_count=near_miss_total,
        bridge_shadow_ready=bridge_shadow_ready,
        preflight_pass=preflight_pass,
        live_blocked_by_env=live_blocked_by_env,
    )

    # Phase 65B: Final decision resolver — priority-based master gate
    final_action, action_reason = resolve_final_action(
        evidence=evidence,
        kill_switch_on=kill_active,
        execution_mode=execution_mode,
        base_action=final_action,
        base_reason=action_reason,
    )

    report = {
        "mode": "hourly_alert",
        "timestamp": ts,
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "bingx_contracts_discovered": total_contracts,
        "crypto_only_perps": crypto_perps,
        "excluded_non_crypto": crypto_excluded,
        "directional_theses": directional_theses,
        "signal_integrity": {
            "deduplicated_candidates_removed": dedup_removed,
            "executable_downgraded_count": exec_downgraded,
            "validated_executable_after": exec_after,
        },
        "long_theses": long_theses,
        "short_theses": short_theses,
        "dux_scan_symbols": dux_scan_size,
        "symbol_timeframes_scanned": st_scanned,
        "symbol_timeframes_attempted": st_attempted,
        "scan_duration_seconds": scan_duration,
        "failed_symbol_count": failed_count,
        "api_error_count": api_err_count,
        "tier_a_size": tier_a,
        "tier_b_size": tier_b,
        "tier_c_size": tier_c,
        "diagnostic_executable_count": executable_count,
        "trigger_confirmed_count": trigger_confirmed_ct,
        "arbiter_eligible_count": arbiter_eligible_ct,
        "executable_candidate_count": executable_count,
        "watchlist_ready_count": watchlist_count,
        "near_miss_rr_count": near_miss_rr_ct,
        "near_miss_psychology_count": near_miss_psych_ct,
        "top_rejection_reason": top_rejection,
        "rr_gate_pass_candidates": rr_pass,
        "alpha_score": alpha_score,
        "alpha_elite_candidates": alpha_elite,
        "alpha_watch_candidates": alpha_watch,
        "psychology_score": psych_score,
        "memory_scan_records": memory.get("total_scan_records_stored", 0) if memory else 0,
        "memory_outcomes": memory.get("total_outcomes_evaluated", 0) if memory else 0,
        "trigger_watcher": {
            "candidates_watched": tw_candidates_watched,
            "active_watchlist_size": tw_active_size,
            "waiting": tw_waiting,
            "confirmed": tw_confirmed,
            "invalidated": tw_invalidated,
            "expired": tw_expired,
            "best_confirmed_candidate": {
                "symbol": tw_best_confirmed["symbol"],
                "timeframe": tw_best_confirmed["timeframe"],
                "direction": tw_best_confirmed["direction"],
                "rr": tw_best_confirmed.get("rr"),
                "thesis_score": tw_best_confirmed.get("thesis_score"),
                "trigger_status": tw_best_confirmed.get("trigger_status"),
                "reason": tw_best_confirmed.get("reason", ""),
            } if tw_best_confirmed else None,
            "best_waiting_candidate": {
                "symbol": tw_best_waiting["symbol"],
                "timeframe": tw_best_waiting["timeframe"],
                "direction": tw_best_waiting["direction"],
                "rr": tw_best_waiting.get("rr"),
                "thesis_score": tw_best_waiting.get("thesis_score"),
            } if tw_best_waiting else None,
        },
        "candidate_arbiter": {
            "shadow_eligible": arbiter_shadow_eligible,
            "review_candidate": arbiter_review_candidate,
            "do_not_trade": arbiter_do_not_trade,
            "has_shadow_eligible_candidates": arbiter_shadow_eligible_found,
            "psychology_alpha_best_candidate_verdict": arbiter_psych_verdict,
            "best_candidate": {
                "symbol": arbiter_best["symbol"],
                "timeframe": arbiter_best["timeframe"],
                "direction": arbiter_best["direction"],
                "rr": arbiter_best["rr"],
                "thesis_score": arbiter_best["thesis_score"],
                "trigger_status": arbiter_best["trigger_status"],
            } if arbiter_best else None,
        },
        "memory_pending": memory.get("pending_outcomes", 0) if memory else 0,
        "memory_best_pattern": ((memory.get("historical_edge_summary") or {}).get("best_pattern") or {}).get("name") if memory else None,
        "memory_worst_pattern": ((memory.get("historical_edge_summary") or {}).get("worst_pattern") or {}).get("name") if memory else None,
        "memory_overall_tf_rate": (memory.get("historical_edge_summary") or {}).get("overall_target_first_rate", 0) if memory else None,
        "best_candidate": {
            "symbol": best["symbol"],
            "timeframe": best["timeframe"],
            "pattern_name": best["pattern_name"],
            "direction": best["direction"],
            "rr_2": best["rr_2"],
            "verdict": best["verdict"],
        } if best else None,
        "alpha_best_candidate": {
            "symbol": alpha_best["symbol"],
            "timeframe": alpha_best["timeframe"],
            "pattern_name": alpha_best["pattern_name"],
            "alpha_score": alpha_best["alpha_score"],
            "verdict": alpha_best["verdict"],
        } if alpha_best else None,
        "dux_decision": dux_decision,
        "alpha_decision": alpha_decision,
        "shadow_decision": shadow_decision,
        "live_decision": live_decision,
        "execution_mode": execution_mode,
        "bridge_shadow_ready": bridge_shadow_ready,
        "bridge_candidate": (lambda si: {
            "symbol": si.get("symbol", "?"),
            "side": si.get("side", "?"),
            "entry": si.get("entry", "?"),
            "stop_loss": si.get("stop_loss", "?"),
            "final_target": si.get("final_target", "?"),
            "rr_final": si.get("rr_final", "?"),
            "risk_usdt": si.get("risk_usdt", 0),
        })(shadow.get("shadow_order_intent", {})) if bridge_shadow_ready and shadow and shadow.get("shadow_order_intent") else None,
        "preflight_decision": preflight_decision,
        "preflight_pass": preflight_pass,
        "live_blocked_by_env": live_blocked_by_env,
        "live_armed": live_armed,
        "open_positions": open_positions,
        "api_credentials_found": api_ok,
        "kill_switch": "ON" if kill_active else "OFF",
        "one_shot_state": one_shot_state,
        "position_open": position_open,
        "emergency": emergency,
        "paper_execution": {
            "status": paper.get("status", "N/A") if paper else "N/A",
            "has_open_trade": bool(paper and paper.get("current_paper_trade") and paper["current_paper_trade"].get("status") == "PAPER_OPEN"),
            "current_paper_trade": paper.get("current_paper_trade") if paper else None,
            "portfolio": paper.get("portfolio") if paper else None,
            "paper_config": paper.get("paper_config") if paper else None,
        } if paper else None,
        "paper_outcome": {
            "verdict": paper_outcome.get("verdict", "N/A") if paper_outcome else "N/A",
            "total_paper_trades": paper_outcome.get("total_paper_trades", 0) if paper_outcome else 0,
            "agg_stats": paper_outcome.get("agg_stats", {}) if paper_outcome else {},
            "current_trade": paper_outcome.get("current_trade") if paper_outcome else None,
        } if paper_outcome else None,
        "candidate_rotation": {
            "next_action": rotation.get("next_action", "N/A") if rotation else "N/A",
            "active_trade_lock_on": rotation.get("active_trade_lock_on", False) if rotation else False,
            "total_candidates_scanned": rotation.get("total_candidates_scanned", 0) if rotation else 0,
            "trigger_confirmed_count": rotation.get("trigger_confirmed_count", 0) if rotation else 0,
            "shadow_eligible_count": rotation.get("shadow_eligible_count", 0) if rotation else 0,
            "best_eligible_candidate": rotation.get("best_eligible_candidate") if rotation else None,
            "best_rejected_candidate": rotation.get("best_rejected_candidate") if rotation else None,
        } if rotation else None,
        "candidate_watchlist": {
            "next_action": watchlist.get("next_action", "N/A") if watchlist else "N/A",
            "active_trade_lock_on": watchlist.get("active_trade_lock_on", False) if watchlist else False,
            "candidate_discovery": watchlist.get("candidate_discovery", {}) if watchlist else {},
            "top_fresh_count": len(watchlist.get("top_fresh_candidates", [])) if watchlist else 0,
            "best_fresh_candidate": watchlist.get("candidate_comparison", {}).get("best_fresh_candidate") if watchlist else None,
            "best_fresh_stronger": watchlist.get("candidate_comparison", {}).get("best_fresh_stronger", False) if watchlist else False,
        } if watchlist else None,
        "paper_rotation": {
            "next_action": paper_rotation.get("next_action", "N/A") if paper_rotation else "N/A",
            "active_trade_lock_on": paper_rotation.get("active_trade_lock_on", False) if paper_rotation else False,
            "rotation_candidate": paper_rotation.get("rotation_candidate") if paper_rotation else None,
            "candidate_discovery": paper_rotation.get("candidate_discovery", {}) if paper_rotation else {},
        } if paper_rotation else None,
        "strategy_evidence": {
            "evidence_verdict": evidence.get("evidence_verdict", "N/A") if evidence else "N/A",
            "closed_trades": evidence.get("closed_trades", 0) if evidence else 0,
            "win_rate": evidence.get("win_rate", 0) if evidence else 0,
            "average_r": evidence.get("average_r", 0) if evidence else 0,
            "total_r": evidence.get("total_r", 0) if evidence else 0,
            "max_drawdown_usdt": evidence.get("max_drawdown_usdt", 0) if evidence else 0,
            "live_allowed": evidence.get("live_allowed", False) if evidence else False,
            "live_reason": evidence.get("live_reason", "evidence lock not run") if evidence else "evidence lock not run",
            "has_anomaly": evidence.get("has_anomaly", False) if evidence else False,
        } if evidence else None,
        "final_action": final_action,
        "action_reason": action_reason,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    # Append to alert ledger
    alert_entry = {
        "timestamp": ts,
        "final_action": final_action,
        "dux_decision": dux_decision,
        "alpha_decision": alpha_decision,
        "alpha_score": alpha_score,
        "shadow_decision": shadow_decision,
        "rr_gate_pass": rr_pass,
        "kill_switch": "ON" if kill_active else "OFF",
    }
    with open(ALERT_LEDGER, "a") as f:
        f.write(json.dumps(alert_entry) + "\n")

    _write_text_report(report, final_action, action_reason)
    return report


def _write_text_report(report: dict, action: str, reason: str):
    best = report.get("best_candidate")
    alpha_best = report.get("alpha_best_candidate")
    lines = [
        "=" * 60,
        "  HOURLY FINAL STATUS",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  BingX contracts discovered: {report['bingx_contracts_discovered']}",
        f"  Excluded non-crypto:        {report.get('excluded_non_crypto', 0)}",
        f"  Crypto-only perps:          {report.get('crypto_only_perps', 0)}",
        f"  Directional theses:         {report.get('directional_theses', 0)}",
        f"    LONG/SHORT:               {report.get('long_theses', 0)}/{report.get('short_theses', 0)}",
        f"  Dux scan symbols:           {report['dux_scan_symbols']}",
        f"  Symbol-timeframes scanned:  {report['symbol_timeframes_scanned']}",
        f"  Symbol-timeframes attempted: {report.get('symbol_timeframes_attempted', report['symbol_timeframes_scanned'])}",
        f"  Scan duration (s):           {report.get('scan_duration_seconds', 0)}",
        f"  Failed symbols:              {report.get('failed_symbol_count', 0)}",
        f"  Tier A/B/C:                  {report.get('tier_a_size', 0)}/{report.get('tier_b_size', 0)}/{report.get('tier_c_size', 0)}",
        f"  RR >= 4 candidates:          {report['rr_gate_pass_candidates']}",
        "",
    ]
    alpha_score = report.get("alpha_score")
    alpha_elite = report.get("alpha_elite_candidates", 0)
    alpha_watch = report.get("alpha_watch_candidates", 0)
    if alpha_score is not None:
        lines += [
            f"  Alpha Score (best): {alpha_score}/100",
            f"  Alpha WATCH >= 70:  {alpha_watch}",
            f"  Alpha ELITE >= 85:  {alpha_elite}",
            "",
        ]
    else:
        lines += ["  Alpha Score: NONE", ""]
    psych_score = report.get("psychology_score")
    if psych_score is not None:
        lines += [f"  Psychology Score:   {psych_score}/100", ""]
    else:
        lines += ["  Psychology Score: NONE", ""]

    exec_count = report.get("diagnostic_executable_count", report.get("executable_candidate_count", 0))
    trigger_ct = report.get("trigger_confirmed_count", 0)
    arbiter_ct = report.get("arbiter_eligible_count", 0)
    wl_count = report.get("watchlist_ready_count", 0)
    nm_rr = report.get("near_miss_rr_count", 0)
    nm_psych = report.get("near_miss_psychology_count", 0)
    top_rej = report.get("top_rejection_reason", "N/A")
    si = report.get("signal_integrity", {})
    dedup_removed = si.get("deduplicated_candidates_removed", 0)
    exec_downgraded = si.get("executable_downgraded_count", 0)
    if exec_count > 0 or wl_count > 0 or nm_rr > 0 or nm_psych > 0 or trigger_ct > 0 or arbiter_ct > 0:
        lines += [
            "  NEAR-MISS DIAGNOSTICS:",
            f"    Diagnostic executable:     {exec_count}",
            f"    Trigger confirmed:         {trigger_ct}",
            f"    Arbiter eligible:          {arbiter_ct}",
            f"    Watchlist-ready:           {wl_count}",
            f"    Near-miss RR:              {nm_rr}",
            f"    Near-miss psychology:      {nm_psych}",
            f"    Top rejection reason:      {top_rej}",
            "",
        ]
    if dedup_removed > 0 or exec_downgraded > 0:
        lines += [
            "  SIGNAL INTEGRITY:",
            f"    Deduplicated removed:     {dedup_removed}",
            f"    Executable downgraded:    {exec_downgraded}",
            f"    Validated executables:    {si.get('validated_executable_after', exec_count)}",
            "",
        ]

    # Trigger watcher section
    tw = report.get("trigger_watcher", {})
    if tw:
        tw_best_conf = tw.get("best_confirmed_candidate")
        tw_best_wait = tw.get("best_waiting_candidate")
        lines += [
            "  TRIGGER WATCHER:",
            f"    Watched candidates:    {tw.get('candidates_watched', 0)}",
            f"    Active watchlist:      {tw.get('active_watchlist_size', 0)}",
            f"    Waiting:               {tw.get('waiting', 0)}",
            f"    TRIGGER_CONFIRMED:     {tw.get('confirmed', 0)}",
            f"    INVALIDATED:           {tw.get('invalidated', 0)}",
            f"    EXPIRED:               {tw.get('expired', 0)}",
        ]
        if tw_best_conf:
            lines += [
                f"    Best confirmed: {tw_best_conf.get('symbol', '?')} {tw_best_conf.get('timeframe', '?')} "
                f"{tw_best_conf.get('direction', '?')} RR:{tw_best_conf.get('rr', '?')} "
                f"Score:{tw_best_conf.get('thesis_score', '?')}",
                f"      Reason: {tw_best_conf.get('reason', '')}",
            ]
        elif tw_best_wait:
            lines += [
                f"    Best waiting:  {tw_best_wait.get('symbol', '?')} {tw_best_wait.get('timeframe', '?')} "
                f"{tw_best_wait.get('direction', '?')} RR:{tw_best_wait.get('rr', '?')}",
            ]
        lines += [""]

    # Candidate arbiter section
    arb = report.get("candidate_arbiter", {})
    if arb:
        arb_shadow = arb.get("shadow_eligible", 0)
        arb_review = arb.get("review_candidate", 0)
        arb_dnt = arb.get("do_not_trade", 0)
        arb_any = arb.get("has_shadow_eligible_candidates", False)
        arb_best = arb.get("best_candidate")
        lines += [
            "  CANDIDATE ARBITER:",
            f"    Shadow eligible:      {arb_shadow}",
            f"    Review candidates:    {arb_review}",
            f"    Do not trade:         {arb_dnt}",
            f"    Shadow eligible YES/NO: {'YES' if arb_any else 'NO'}",
        ]
        if arb_best:
            lines += [
                f"    Best: {arb_best['symbol']} {arb_best['timeframe']} {arb_best['direction']} "
                f"RR:1:{arb_best['rr']} Score:{arb_best['thesis_score']} Trigger:{arb_best['trigger_status']}",
            ]
        lines += [
            f"    Psych alpha verdict:  {arb.get('psychology_alpha_best_candidate_verdict', 'N/A')}",
            "",
        ]

    # Unified Candidate Bridge section (Phase 50) — read from arbiter report directly
    arbiter_report = _read_json(os.path.join(RESULTS_DIR, "candidate_arbiter_report.json"))
    ub = arbiter_report.get("unified_bridge_candidates", {}) if arbiter_report else {}
    if ub and ub.get("trigger_confirmed_count", 0) > 0:
        ub_list = ub.get("candidates", [])
        best_bridge = None
        for bc in ub_list:
            if bc.get("verdict") == "SHADOW_ELIGIBLE":
                best_bridge = bc
                break
        if not best_bridge and ub_list:
            best_bridge = max(ub_list, key=lambda x: (x.get("rr", 0), x.get("thesis_score", 0)))
        lines += [
            "  UNIFIED CANDIDATE BRIDGE:",
            f"    Trigger confirmed candidates: {ub['trigger_confirmed_count']}",
            f"    Shadow eligible from trigger:  {ub['shadow_eligible_from_trigger']}",
            f"    Review candidate from trigger: {ub['review_candidate_from_trigger']}",
        ]
        if best_bridge:
            lines += [
                f"    Best bridge candidate: {best_bridge['symbol']} {best_bridge['timeframe']} "
                f"{best_bridge['direction']} RR:1:{best_bridge.get('rr', '?')} "
                f"Score:{best_bridge.get('thesis_score', '?')}",
                f"      Status: {best_bridge.get('verdict', 'DO_NOT_TRADE')}",
            ]
        lines += [""]

    mem_records = report.get("memory_scan_records", 0)
    mem_outcomes = report.get("memory_outcomes", 0)
    mem_pending = report.get("memory_pending", 0)
    if mem_records > 0 or mem_outcomes > 0:
        mp_best = report.get("memory_best_pattern") or "N/A"
        mp_worst = report.get("memory_worst_pattern") or "N/A"
        mp_tf = report.get("memory_overall_tf_rate") or 0
        lines += [
            "  PSYCHOLOGY MEMORY:",
            f"    Records: {mem_records}  Outcomes: {mem_outcomes}  Pending: {mem_pending}",
            f"    Best pattern: {mp_best}  Worst: {mp_worst}",
            f"    Overall TF rate: {mp_tf:.4f}",
            "",
        ]

    # Phase 51: TRIGGER BRIDGE active indicator
    bridge_candidate_shown = False
    if report.get("bridge_shadow_ready"):
        bc = report.get("bridge_candidate")
        if bc:
            lines += [
                "  TRIGGER BRIDGE — SHADOW_READY",
                "    Symbol:   %s %s" % (bc.get("symbol", "?"), bc.get("side", "?")),
                "    Entry:    %s  Stop: %s  Target: %s" % (bc.get("entry", "?"), bc.get("stop_loss", "?"), bc.get("final_target", "?")),
                "    RR:       1:%s  Risk: %s USDT" % (bc.get("rr_final", "?"), bc.get("risk_usdt", 0)),
                "",
            ]
        else:
            lines += [
                "  TRIGGER BRIDGE ACTIVE — SHADOW_READY",
                "",
            ]
        bridge_candidate_shown = True

    # Phase 55: Preflight section
    pf_dec = report.get("preflight_decision", "N/A")
    pf_pass = report.get("preflight_pass", False)
    if pf_dec != "N/A":
        lines += [
            "  LIVE MICRO PREFLIGHT:",
            f"    Decision: {pf_dec}",
            f"    Result:   {'All checks PASS' if pf_pass else 'Checks FAILED'}",
            "",
        ]

    # Phase 56: One-shot live guard
    os_state = report.get("one_shot_state", "N/A")
    lines += [
        "  ONE SHOT LIVE GUARD:",
        f"    State:    {os_state}",
        "",
    ]

    # Phase 59: Paper execution ledger
    paper_exec = report.get("paper_execution")
    if paper_exec and paper_exec.get("status", "N/A") != "N/A":
        lines += [
            "  PAPER EXECUTION:",
            f"    Status:         {paper_exec['status']}",
        ]
        pt = paper_exec.get("current_paper_trade")
        if pt:
            lines += [
                f"    Symbol:         {pt.get('symbol', 'N/A')}",
                f"    Side:           {pt.get('side', 'N/A')}",
                f"    Entry:          {pt.get('entry', 0)}",
                f"    Stop:           {pt.get('stop', 0)}",
                f"    Target:         {pt.get('target', 0)}",
                f"    Quantity:       {pt.get('quantity', 0)}",
                f"    Notional:       {pt.get('notional', 0)} USDT",
                f"    Risk:           {pt.get('risk', 0)} USDT",
                f"    RR:             1:{pt.get('rr', 0)}",
                f"    Trade Status:   {pt.get('status', 'N/A')}",
                f"    Entry Filled:   {'YES' if pt.get('entry_fill_check') else 'NO'}",
            ]
            if pt.get("unrealized_pnl") is not None:
                lines.append(f"    Unrealized P&L: {pt['unrealized_pnl']:.2f} USDT")
            if pt.get("realized_pnl") is not None:
                lines.append(f"    Realized P&L:   {pt['realized_pnl']:.2f} USDT")
            if pt.get("exit_reason"):
                lines.append(f"    Exit Reason:    {pt['exit_reason']}")
        lines += [""]

    # Phase 60: Paper trade outcome validator
    po = report.get("paper_outcome")
    if po and po.get("verdict", "N/A") != "N/A":
        lines += [
            "  PAPER TRADE OUTCOME:",
            f"    Verdict:            {po['verdict']}",
            f"    Total Paper Trades: {po['total_paper_trades']}",
        ]
        agg = po.get("agg_stats", {})
        if agg:
            lines += [
                f"    Closed: {agg.get('total_closed', 0)}  "
                f"Wins: {agg.get('wins', 0)}  "
                f"Losses: {agg.get('losses', 0)}  "
                f"WR: {agg.get('win_rate', 0)}%",
                f"    Total P&L: {agg.get('total_pnl', 0):.2f} USDT  "
                f"Avg R: {agg.get('average_r', 0)}  "
                f"Max Loss: {agg.get('max_loss', 0):.2f}  "
                f"Consec Losses: {agg.get('consecutive_losses', 0)}",
            ]
        oct = po.get("current_trade")
        if oct:
            lines += [
                f"    Current: {oct.get('symbol', 'N/A')} {oct.get('side', 'N/A')} "
                f"{oct.get('status', 'N/A')} {oct.get('hit_reason') or ''}",
            ]
        lines += [""]

    # Phase 61: Candidate rotation report
    rot = report.get("candidate_rotation")
    if rot and rot.get("next_action", "N/A") != "N/A":
        lines += [
            "  CANDIDATE ROTATION:",
            f"    Next Action:        {rot['next_action']}",
            f"    Trade Lock:         {'ON' if rot.get('active_trade_lock_on') else 'OFF'}",
            f"    Total Candidates:   {rot.get('total_candidates_scanned', 0)}",
            f"    Trigger Confirmed:  {rot.get('trigger_confirmed_count', 0)}",
            f"    Shadow Eligible:    {rot.get('shadow_eligible_count', 0)}",
        ]
        be = rot.get("best_eligible_candidate")
        if be:
            lines.append(
                f"    Best Eligible:      {be.get('symbol','?')} {be.get('direction','?')} "
                f"RR:{be.get('rr','?')} Score:{be.get('thesis_score','?')}"
            )
        br = rot.get("best_rejected_candidate")
        if br:
            lines.append(
                f"    Best Rejected:      {br.get('symbol','?')} {br.get('direction','?')} "
                f"Reason: {br.get('rejection_reason_display','?')}"
            )
        lines += [""]

    # Phase 62: Paper candidate watchlist
    wl = report.get("candidate_watchlist")
    if wl and wl.get("next_action", "N/A") != "N/A":
        cd = wl.get("candidate_discovery", {})
        bf = wl.get("best_fresh_candidate")
        lines += [
            "  PAPER CANDIDATE WATCHLIST:",
            f"    Next Action:   {wl['next_action']}",
            f"    Trade Lock:    {'ON' if wl.get('active_trade_lock_on') else 'OFF'}",
            f"    Total:         {cd.get('total_candidates',0)}  "
            f"Confirmed: {cd.get('trigger_confirmed',0)}  "
            f"Eligible: {cd.get('shadow_eligible',0)}",
        ]
        if bf:
            lines.append(
                f"    Best Fresh:    {bf.get('symbol','?')} {bf.get('direction','?')} "
                f"RR:{bf.get('rr','?')} Score:{bf.get('thesis_score','?')} "
                f"{'STRONGER' if wl.get('best_fresh_stronger') else 'weaker'}"
            )
        lines += [""]

    # Phase 63: Paper rotation engine
    pr = report.get("paper_rotation")
    if pr and pr.get("next_action", "N/A") != "N/A":
        lines += [
            "  PAPER ROTATION ENGINE:",
            f"    Next Action:   {pr['next_action']}",
            f"    Trade Lock:    {'ON' if pr.get('active_trade_lock_on') else 'OFF'}",
            f"    Portfolio:     {pr.get('active_trades_count',0)} / {pr.get('max_paper_trades',5)} active, "
            f"{pr.get('available_slots',0)} slots free",
        ]
        rc = pr.get("rotation_candidate")
        if rc:
            lines.append(
                f"    Rotation:      {rc.get('symbol','?')} {rc.get('direction','?')} "
                f"RR:{rc.get('rr','?')} Score:{rc.get('thesis_score','?')}"
            )
        pcd = pr.get("candidate_discovery", {})
        if pcd:
            lines.append(
                f"    Candidates:    Total {pcd.get('total_candidates',0)}  "
                f"Eligible {pcd.get('eligible_candidates',0)}  "
                f"Fresh {pcd.get('fresh_eligible',0)}"
            )
        rcfg = pr.get("risk_config", {})
        if rcfg:
            lines.append(
                f"    Risk Budget:   Capital {rcfg.get('account_capital_usdt','?')} USDT, "
                f"Max/Trade {rcfg.get('max_risk_per_trade_usdt','?')} USDT"
            )
        lines += [""]

    # Phase 64/66: Paper portfolio & risk config
    paper_exec = report.get("paper_execution")
    portfolio = (paper_exec or {}).get("portfolio")
    paper_cfg = (paper_exec or {}).get("paper_config")
    if portfolio:
        lines += [
            "  PAPER PORTFOLIO:",
            f"    Active: {portfolio.get('active_count', 0)} / {portfolio.get('max_allowed', 5)}",
        ]
        if paper_cfg:
            cap_risk = paper_cfg.get("capital_usdt", "?")
            max_risk_tt = paper_cfg.get("max_risk_per_trade_usdt", "?")
            max_port_notional = paper_cfg.get("max_portfolio_notional_usdt", "?")
            max_lev = paper_cfg.get("max_leverage", "?")
            lines += [
                "  PAPER CAPITAL RISK (Risk vs Notional Model):",
                f"    Capital:                  {cap_risk} USDT",
                f"    Max Risk / Trade:         {max_risk_tt} USDT",
                f"    Max Portfolio Notional:   {max_port_notional} USDT (2x capital)",
                f"    Max Leverage:             {max_lev}x",
            ]
        for t in portfolio.get("active_trades", []):
            lines.append(
                f"    {t.get('symbol','?')} {t.get('side','?')} "
                f"RR:1:{t.get('rr',0)} Entry:{t.get('entry',0)} "
                f"Risk:{t.get('risk',0):.2f} "
                f"P&L:{t.get('unrealized_pnl',0):.2f} "
                f"{'FILLED' if t.get('entry_fill_check') else 'WAITING'}"
            )
        lines.append(
            f"    Risk USDT: {portfolio.get('total_risk_usdt',0):.2f}  "
            f"Notional: {portfolio.get('total_notional_exposure',0):.2f} USDT  "
            f"Lev: {portfolio.get('portfolio_leverage',0):.2f}x  "
            f"Remaining Cap: {portfolio.get('remaining_notional_capacity',0):.2f} USDT  "
            f"Unrealized: {portfolio.get('total_unrealized_pnl',0):.4f} USDT"
        )
        rejected = portfolio.get("rejected_candidates", [])
        if rejected:
            lines += ["", "  Rejected Paper Candidates:"]
            for r in rejected[-5:]:
                lines.append(f"    - {r}")
        lines += [""]

    # Phase 64: Strategy evidence lock
    evidence = _read_json(os.path.join(RESULTS_DIR, "strategy_evidence_report.json"))
    if evidence:
        lines += [
            "  STRATEGY EVIDENCE LOCK:",
            f"    Verdict:        {evidence.get('evidence_verdict', '?')}",
            f"    Closed Trades:  {evidence.get('closed_trades', 0)}",
            f"    Win Rate:       {evidence.get('win_rate', 0)}%",
            f"    Average R:      {evidence.get('average_r', 0)}",
            f"    Total R:        {evidence.get('total_r', 0)}",
            f"    Max Drawdown:   {evidence.get('max_drawdown_usdt', 0):.2f} USDT",
            f"    Live Allowed:   {'NO' if not evidence.get('live_allowed') else 'MANUAL REVIEW REQUIRED'}",
            f"    Reason:         {evidence.get('live_reason', '?')}",
            "",
        ]

    if best and not bridge_candidate_shown:
        lines += [
            "  BEST CANDIDATE:",
            f"    {best['pattern_name']} on {best['symbol']} {best['timeframe']}",
            f"    Direction: {best['direction']}  RR: 1:{best['rr_2']}",
            f"    Verdict:   {best['verdict']}",
            "",
        ]
    elif not bridge_candidate_shown:
        lines += ["  BEST CANDIDATE: NONE", ""]

    if alpha_best:
        lines += [
            "  ALPHA BEST:",
            f"    {alpha_best['pattern_name']} on {alpha_best['symbol']} {alpha_best['timeframe']}",
            f"    Alpha Score: {alpha_best['alpha_score']}/100  Verdict: {alpha_best['verdict']}",
            "",
        ]

    lines += [
        f"  Dux Decision:       {report['dux_decision']}",
        f"  Alpha Decision:     {report['alpha_decision']}",
        f"  Shadow Decision:    {report['shadow_decision']}",
        f"  Live Decision:      {report['live_decision']}",
        f"  Execution Mode:     {report['execution_mode']}",
        f"  Live Armed:         {'YES' if report['live_armed'] else 'NO'}",
        f"  Open Positions:     {report['open_positions']}",
        f"  Position Monitor:   {'OPEN' if report.get('position_open') else 'CLOSED'}",
        f"  Emergency:          {'YES' if report.get('emergency') else 'NO'}",
        f"  API Credentials:    {'FOUND' if report['api_credentials_found'] else 'NOT FOUND'}",
        f"  Kill Switch:        {report['kill_switch']}",
        "",
        f"  FINAL ACTION: {action}",
        f"  REASON: {reason}",
        "",
        "  WARNING: This system is not approved for live trading.",
        "",
        "  Useful files:",
        "    deploy_results/hourly_status.txt",
        "    deploy_results/doctor_daily_packet.txt",
        "    deploy_results/bingx_live_execution.txt",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    print(f"[LEDGER] {ALERT_LEDGER}")


def main():
    report = run_hourly_alert()
    return 0


if __name__ == "__main__":
    sys.exit(main())
