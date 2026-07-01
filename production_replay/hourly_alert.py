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
) -> tuple[str, str]:
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
    open_positions = live.get("open_position_count", 0) if live else 0
    kill_active = _kill_switch_active()
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

    final_action, action_reason = _determine_final_action(
        dux_decision, rr_pass, alpha_score, alpha_decision,
        shadow_decision, live_decision, live_armed, execution_mode,
        position_open=position_open, emergency=emergency,
        executable_count=executable_count,
        watchlist_count=watchlist_count,
        near_miss_count=near_miss_total,
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
        "live_armed": live_armed,
        "open_positions": open_positions,
        "api_credentials_found": api_ok,
        "kill_switch": "ON" if kill_active else "OFF",
        "position_open": position_open,
        "emergency": emergency,
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

    if best:
        lines += [
            "  BEST CANDIDATE:",
            f"    {best['pattern_name']} on {best['symbol']} {best['timeframe']}",
            f"    Direction: {best['direction']}  RR: 1:{best['rr_2']}",
            f"    Verdict:   {best['verdict']}",
            "",
        ]
    else:
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
