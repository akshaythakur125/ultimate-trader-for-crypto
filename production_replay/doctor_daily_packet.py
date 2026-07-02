"""Final doctor daily packet — one-command combined status.

Runs (or reads outputs from) healthcheck, today_trade_plan,
and manual_risk_console, then produces a single short doctor-friendly
report with multi-candidate scanner results.

Usage:
    python -m production_replay.doctor_daily_packet
"""

import json, os, subprocess, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
LEDGER_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
STATE_DIR = LEDGER_DIR  # alias for runtime_state
LEDGER_FILE = os.environ.get("EVIDENCE_LEDGER_PATH") or os.path.join(LEDGER_DIR, "evidence_ledger.jsonl")
TXT_PATH = os.path.join(RESULTS_DIR, "doctor_daily_packet.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "doctor_daily_packet.json")

MIN_TRADES = 100
MIN_DAYS = 30


def _read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _read_ledger_latest() -> dict | None:
    if not os.path.exists(LEDGER_FILE):
        return None
    with open(LEDGER_FILE) as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def _run_module(name: str, *extra_args: str) -> bool:
    try:
        cmd = [sys.executable, "-m", name, *extra_args]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0
    except Exception:
        return False


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    _run_module("production_replay.healthcheck")
    _run_module("production_replay.today_trade_plan")
    _run_module("production_replay.manual_risk_console")
    _run_module("production_replay.strategy_tournament")
    _run_module("production_replay.dux_pattern_engine")
    _run_module("production_replay.alpha_intelligence")
    _run_module("production_replay.psychology_alpha")
    _run_module("production_replay.psychology_memory")
    _run_module("production_replay.near_miss_diagnostics")
    _run_module("production_replay.bingx_shadow_executor")
    _run_module("production_replay.bingx_live_preflight")
    _run_module("production_replay.bingx_live_micro_executor")
    _run_module("production_replay.bingx_position_monitor", "--once")
    _run_module("production_replay.hourly_alert")

    trade_plan = _read_json(os.path.join(RESULTS_DIR, "today_trade_plan.json"))
    risk_plan = _read_json(os.path.join(RESULTS_DIR, "manual_risk_plan.json"))
    tournament = _read_json(os.path.join(RESULTS_DIR, "strategy_tournament_report.json"))
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    alpha = _read_json(os.path.join(RESULTS_DIR, "alpha_intelligence_report.json"))
    psych = _read_json(os.path.join(RESULTS_DIR, "psychology_alpha_report.json"))
    memory = _read_json(os.path.join(RESULTS_DIR, "psychology_memory_report.json"))
    near_miss = _read_json(os.path.join(RESULTS_DIR, "near_miss_report.json"))
    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    live = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))
    preflight = _read_json(os.path.join(RESULTS_DIR, "bingx_live_preflight.json"))
    pos_mon = _read_json(os.path.join(RESULTS_DIR, "position_monitor_status.json"))
    hourly = _read_json(os.path.join(RESULTS_DIR, "hourly_status.json"))
    entry = _read_ledger_latest()

    if entry:
        trades = entry.get("total_trades", 0)
        days = entry.get("calendar_days", 0)
        safety_ok = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED"
        launch_ok = entry.get("launch_check_verdict") == "PASS"
        kill = entry.get("kill_status") == "KILL"
        live_ok = not entry.get("live_trading_enabled", False)
        paper_ok = not entry.get("paper_trading_enabled", False)
    else:
        trades = 0; days = 0
        safety_ok = True; launch_ok = True
        kill = False; live_ok = True; paper_ok = True

    system_safe = safety_ok and launch_ok

    # Read candidates from trade plan
    candidates = []
    selected_label = None
    selected_levels = {}
    if trade_plan:
        candidates = trade_plan.get("candidates", [])
        selected_label = trade_plan.get("selected_candidate")
        selected_levels = trade_plan.get("selected_levels", {})

    if risk_plan:
        pos_sizing = risk_plan.get("position_sizing", {})
    else:
        pos_sizing = {"position_size": None, "risk_distance": None, "max_loss_if_hit": None, "warning": None}

    # Decision
    decision = "MANUAL_REVIEW_ONLY"
    reasons = []

    if not safety_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("safety lock failed")
    if not launch_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("launch check failed")
    if not live_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("live trading not disabled")
    if not paper_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("paper trading not disabled")
    if kill:
        decision = "DO_NOT_TRADE"
        reasons.append("kill switch triggered")
    if trade_plan and trade_plan.get("trade_decision") == "WAIT" and decision != "DO_NOT_TRADE":
        decision = "DO_NOT_TRADE"
        reasons.append("trade plan says WAIT")
    if selected_label is None:
        if decision != "DO_NOT_TRADE":
            decision = "DO_NOT_TRADE"
        reasons.append("no candidate passes RR gate")
    if trades < MIN_TRADES or days < MIN_DAYS:
        if decision not in ("DO_NOT_TRADE",):
            decision = "MANUAL_REVIEW_ONLY"
        reasons.append(f"evidence incomplete ({trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days)")
    if decision == "MANUAL_REVIEW_ONLY" and not any("evidence" in r for r in reasons):
        reasons.append("evidence gates not met")
    if not reasons:
        reasons.append("all checks pass")

    # Format levels for selected candidate
    entry_str = f"{selected_levels.get('entry_zone'):.2f}" if selected_levels.get("entry_zone") is not None else "N/A"
    stop_str = f"{selected_levels.get('stop'):.2f}" if selected_levels.get("stop") is not None else "N/A"
    t1_str = f"{selected_levels.get('target_1'):.2f}" if selected_levels.get("target_1") is not None else "N/A"
    t2_str = f"{selected_levels.get('target_2'):.2f}" if selected_levels.get("target_2") is not None else "N/A"
    rr_1 = selected_levels.get("rr_1")
    rr_2 = selected_levels.get("rr_2")
    rr1_str = f"1:{rr_1:.2f}" if rr_1 is not None else "N/A"
    rr2_str = f"1:{rr_2:.2f}" if rr_2 is not None else "N/A"

    pos_str = f"{pos_sizing.get('position_size'):.6f}" if pos_sizing.get("position_size") is not None else "N/A"
    loss_str = f"{pos_sizing.get('max_loss_if_hit'):.2f}" if pos_sizing.get("max_loss_if_hit") is not None else "N/A"

    # Candidate table (never empty — show placeholder if no rows)
    cand_lines = []
    if not candidates:
        cand_lines.append("    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            "(no configs)", "", "", "", "", "", "", ""))
    for c in candidates:
        reason = c.get("reason", "")
        cand_lines.append("    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            c["label"], c["direction"], c["rr_t1"], c["rr_t2"],
            c["quality"], c["rr_gate"], c["verdict"], reason[:20]))

    # Tournament section
    tournament_lines = []
    if tournament:
        top_strat = tournament.get("top_strategy")
        if top_strat:
            tournament_lines = [
                "",
                "  TOURNAMENT TOP STRATEGY:",
                f"    {top_strat['display_name']} on {top_strat['config_label']}",
                f"    EV: {top_strat['ev_r']}R  PF: {top_strat['pf']}  WR: {top_strat['win_rate']:.1%}",
                f"    Verdict: {top_strat['verdict']}",
            ]
        else:
            tournament_lines = ["", "  TOURNAMENT: No passing strategy", ""]
        tournament_lines += [
            f"    PASS: {tournament['passing']}  WATCH: {tournament['watching']}  "
            f"REJECT: {tournament['rejected']}  SKIP: {tournament['skipped']}",
        ]

    # Dux pattern engine section
    dux_lines = []
    if dux:
        best_dux = dux.get("best_candidate")
        rr_count = dux.get("rr_gate_pass", 0)
        dux_scan_size = dux.get("dux_scan_universe_size", dux.get("symbols_scanned", 0))
        total_contracts = dux.get("total_raw_contracts", dux.get("total_contracts", 0))
        st_scanned = dux.get("symbol_timeframes_scanned", 0)
        if best_dux:
            dux_lines = [
                "",
                "  DUX-STYLE PATTERN ENGINE:",
                f"    {best_dux['pattern_name']} on {best_dux['symbol']} {best_dux['timeframe']}",
                f"    Direction: {best_dux['direction']}  RR: 1:{best_dux['rr_2']}",
                f"    Stats: {best_dux['stats']['trades']} trades, EV {best_dux['stats']['ev_r']}R",
                f"    Verdict: {best_dux['verdict']}",
            ]
        else:
            dux_lines = ["", "  DUX PATTERN ENGINE: No candidate passes RR >= 4 gate", ""]
        dux_lines += [
            "",
            "  DUX SCAN UNIVERSE:",
            f"    BingX contracts discovered: {total_contracts}",
            f"    Dux scan symbols:           {dux_scan_size}",
            f"    Symbol-timeframes scanned:  {st_scanned}",
            f"    Symbol-timeframes attempted: {dux.get('symbol_timeframes_attempted', st_scanned)}",
            f"    Scan duration (seconds):    {dux.get('scan_duration_seconds', 0)}",
            f"    Failed symbols:             {dux.get('failed_symbol_count', 0)}",
            f"    API errors:                 {dux.get('api_error_count', 0)}",
            f"    RR >= 4 candidates:         {rr_count}",
            f"    Dux decision:               {dux.get('final_decision', 'N/A')}",
        ]

    # Expanded universe scan section
    expanded_lines = []
    if dux:
        t_a = dux.get("tier_a_size", 0)
        t_b = dux.get("tier_b_size", 0)
        t_c = dux.get("tier_c_size", 0)
        if t_a or t_b or t_c:
            expanded_lines = [
                "",
                "  EXPANDED UNIVERSE SCAN:",
                f"    Tier A (5m/15m/30m/1h): {t_a}",
                f"    Tier B (15m/30m/1h):    {t_b}",
                f"    Tier C (30m/1h):         {t_c}",
                f"    Total scan symbols:     {dux_scan_size}",
                f"    Completed symbol-TFs:   {st_scanned}",
                f"    Failed symbols:         {dux.get('failed_symbol_count', 0)}",
                f"    Scan duration:          {dux.get('scan_duration_seconds', 0)}s",
                f"    Scan status:            {'COMPLETE' if dux.get('failed_symbol_count', 0) == 0 and st_scanned > 0 else 'PARTIAL'}",
            ]

    # Alpha intelligence section
    alpha_lines = []
    if alpha:
        best_alpha = alpha.get("best_candidate")
        alpha_score = best_alpha["alpha_score"] if best_alpha else 0
        elite = "YES" if best_alpha and alpha_score >= 85 else "NO"
        if best_alpha:
            alpha_lines = [
                "",
                "  ALPHA INTELLIGENCE:",
                f"    Best: {best_alpha['pattern_name']} on {best_alpha['symbol']} {best_alpha['timeframe']}",
                f"    Alpha Score: {best_alpha['alpha_score']}/100  RR: 1:{best_alpha['rr_2']}",
                f"    Elite Status: {elite}",
                f"    Final Decision: {alpha.get('final_decision', 'N/A')}",
            ]
        else:
            alpha_lines = ["", "  ALPHA INTELLIGENCE: No candidate passes alpha >= 70", ""]
        alpha_lines += [
            "",
            "  ALPHA SCAN:",
            f"    Total patterns:     {alpha.get('total_patterns_detected', 0)}",
            f"    RR >= 4 candidates: {alpha.get('rr_gate_pass_candidates', 0)}",
            f"    Alpha WATCH >= 70:  {alpha.get('alpha_watch_candidates', 0)}",
            f"    Alpha ELITE >= 85:  {alpha.get('alpha_elite_candidates', 0)}",
        ]
    else:
        alpha_lines = ["", "  ALPHA INTELLIGENCE: MISSING (no report)", ""]

    # Deep psychology alpha section
    psych_lines = []
    if psych:
        best_psych = psych.get("best_candidate")
        psych_score = best_psych["psychology_score"] if best_psych else 0
        if best_psych:
            psych_lines = [
                "",
                "  MARKET PSYCHOLOGY ALPHA:",
                f"    Best: {best_psych['pattern_name']} on {best_psych['symbol']} {best_psych['timeframe']}",
                f"    Thesis: {best_psych.get('psychology_thesis', 'N/A')}",
                f"    Psychology Score: {psych_score}/100  RR: 1:{best_psych['rr_2']}",
                f"    Elite: {'YES' if psych_score >= 85 else 'NO'}",
                f"    Final Decision: {psych.get('final_decision', 'N/A')}",
            ]
        else:
            psych_lines = ["", "  MARKET PSYCHOLOGY ALPHA: No candidate passes >= 70", ""]
        psych_lines += [
            "",
            "  PSYCHOLOGY SCAN:",
            f"    Total patterns:     {psych.get('total_patterns_detected', 0)}",
            f"    RR >= 4 candidates: {psych.get('rr_gate_pass_candidates', 0)}",
            f"    WATCH >= 70:        {psych.get('psychology_watch_candidates', 0)}",
            f"    ELITE >= 85:        {psych.get('psychology_elite_candidates', 0)}",
        ]
    else:
        psych_lines = ["", "  MARKET PSYCHOLOGY ALPHA: MISSING (no report)", ""]

    # Psychology memory section
    memory_lines = []
    if memory:
        hes = memory.get("historical_edge_summary", {})
        mem_records = memory.get("total_scan_records_stored", 0)
        mem_outcomes = memory.get("total_outcomes_evaluated", 0)
        mem_pending = memory.get("pending_outcomes", 0)
        best_pat = hes.get("best_pattern", {})
        worst_pat = hes.get("worst_pattern", {})
        best_pat_name = best_pat.get("name", "N/A") if best_pat else "N/A"
        worst_pat_name = worst_pat.get("name", "N/A") if worst_pat else "N/A"
        memory_lines = [
            "",
            "  PSYCHOLOGY MEMORY:",
            f"    Scan records stored: {mem_records}",
            f"    Outcomes evaluated:  {mem_outcomes}",
            f"    Pending outcomes:    {mem_pending}",
            f"    Best pattern:        {best_pat_name}",
            f"    Worst pattern:       {worst_pat_name}",
        ]
        dangerous = hes.get("dangerous_symbols", [])
        reliable = hes.get("reliable_symbols", [])
        if dangerous:
            memory_lines.append(f"    Dangerous symbols:  {', '.join(dangerous[:5])}")
        if reliable:
            memory_lines.append(f"    Reliable symbols:   {', '.join(reliable[:5])}")
        memory_lines.append(f"    Historical edge:    {hes.get('overall_target_first_rate', 0):.4f} TF rate")
    else:
        memory_lines = ["", "  PSYCHOLOGY MEMORY: MISSING (no report)", ""]

    # Near-miss diagnostics section
    near_miss_lines = []
    if near_miss:
        bkt = near_miss.get("bucket_counts", {})
        rej = near_miss.get("rejection_reason_counts", {})
        lc = near_miss.get("lifecycle_counts", {})
        best_wl = near_miss.get("best_watchlist_candidate")
        top_rej = near_miss.get("top_rejection_reason", "N/A")
        crypto_excluded = near_miss.get("excluded_non_crypto", 0)
        directional = near_miss.get("directional_theses_created", 0)
        long_ct = near_miss.get("long_theses", 0)
        short_ct = near_miss.get("short_theses", 0)
        dedup_removed = near_miss.get("deduplicated_candidates_removed", 0)
        exec_before = near_miss.get("validated_executable_before", 0)
        exec_after = near_miss.get("validated_executable_after", 0)
        near_miss_lines = [
            "",
            "  SIGNAL INTEGRITY:",
            f"    Crypto-only filter:        {'PASS' if crypto_excluded > 0 else 'NO EXCLUSIONS'}",
            f"    Non-crypto excluded:       {crypto_excluded}",
            f"    Duplicate candidates removed: {dedup_removed}",
            f"    Executable before validation: {exec_before}",
            f"    Executable after validation:  {exec_after}",
            f"    Trigger confirmed promoted:   {near_miss.get('trigger_confirmed_promoted', 0)}",
            f"    Trigger invalidated:          {near_miss.get('trigger_invalidated', 0)}",
            "",
            "  CRYPTO-ONLY + THESIS SECTION:",
            f"    Excluded non-crypto symbols: {crypto_excluded}",
            f"    Directional theses:         {directional}",
            f"      LONG theses:              {long_ct}",
            f"      SHORT theses:             {short_ct}",
            "",
            "  NEAR-MISS DIAGNOSTICS:",
            f"    Diagnostic executable:    {bkt.get('DIAGNOSTIC_EXECUTABLE', 0)}",
            f"    Trigger confirmed:        {bkt.get('TRIGGER_CONFIRMED', 0)}",
            f"    Arbiter eligible:         {bkt.get('ARBITER_ELIGIBLE', 0)}",
            f"    Watchlist-ready:          {bkt.get('WATCHLIST_READY', 0)}",
            f"    Near-miss RR:             {bkt.get('NEAR_MISS_RR', 0)}",
            f"    Near-miss psychology:     {bkt.get('NEAR_MISS_PSYCHOLOGY', 0)}",
            f"    Raw trap detected:        {bkt.get('RAW_TRAP_DETECTED', 0)}",
            f"    Top rejection reason:     {top_rej}",
        ]
        for reason, count in sorted(rej.items(), key=lambda x: -x[1]):
            if count > 0:
                near_miss_lines.append(f"      {reason}: {count}")
        for stage, count in sorted(lc.items(), key=lambda x: -x[1]):
            if count > 0:
                near_miss_lines.append(f"      Lifecycle {stage}: {count}")
        if best_wl:
            thesis_type = best_wl.get("thesis_type", best_wl.get("pattern_name", "N/A"))
            direction = best_wl.get("direction", "N/A")
            psy = best_wl.get("psychology_score", "N/A")
            rr = best_wl.get("current_rr", "N/A")
            nxt = best_wl.get("next_step", best_wl.get("thesis_invalidation", "N/A"))
            thesis_score = best_wl.get("trade_thesis_score", "N/A")
            near_miss_lines += [
                f"    Best watchlist: {thesis_type} on {best_wl.get('symbol', 'N/A')} {best_wl.get('timeframe', 'N/A')}",
                f"    Direction: {direction}  RR: {rr}  Psych: {psy}  Thesis Score: {thesis_score}",
                f"    What must happen next: {nxt}",
            ]
    else:
        near_miss_lines = ["", "  NEAR-MISS DIAGNOSTICS: MISSING (no report)", ""]

    # Trigger watcher section
    trigger_lines = []
    trigger_watcher = _read_json(os.path.join(RESULTS_DIR, "trigger_watcher_report.json"))
    trigger_active = _read_json(os.path.join(LEDGER_DIR, "trigger_watchlist_active.json"))
    if trigger_watcher:
        tw_best_conf = trigger_watcher.get("best_confirmed_candidate")
        tw_best_wait = trigger_watcher.get("best_waiting_candidate")
        trigger_lines = [
            "",
            "  TRIGGER WATCHER:",
            f"    Watched candidates:    {trigger_watcher.get('candidates_watched', 0)}",
            f"    Active watchlist:      {trigger_active.get('total_active', 0) if trigger_active else 0}",
            f"    Waiting:               {trigger_watcher.get('waiting_count', 0)}",
            f"    TRIGGER_CONFIRMED:     {trigger_watcher.get('confirmed_count', 0)}",
            f"    INVALIDATED:           {trigger_watcher.get('invalidated_count', 0)}",
            f"    EXPIRED:               {trigger_watcher.get('expired_count', 0)}",
        ]
        if tw_best_conf:
            trigger_lines += [
                f"    Best confirmed: {tw_best_conf.get('symbol', '?')} {tw_best_conf.get('timeframe', '?')} "
                f"{tw_best_conf.get('direction', '?')} RR:{tw_best_conf.get('rr', '?')} "
                f"Score:{tw_best_conf.get('thesis_score', '?')}",
                f"      Reason: {tw_best_conf.get('reason', '')}",
            ]
        elif tw_best_wait:
            trigger_lines += [
                f"    Best waiting:  {tw_best_wait.get('symbol', '?')} {tw_best_wait.get('timeframe', '?')} "
                f"{tw_best_wait.get('direction', '?')} RR:{tw_best_wait.get('rr', '?')}",
            ]
    else:
        trigger_lines = ["", "  TRIGGER WATCHER: MISSING (no report)", ""]

    # Candidate arbiter section
    arbiter_lines = []
    arbiter = _read_json(os.path.join(RESULTS_DIR, "candidate_arbiter_report.json"))
    if arbiter:
        arb_best = arbiter.get("best_candidate")
        arbiter_lines = [
            "",
            "  CANDIDATE ARBITER:",
            f"    Total evaluated:       {arbiter.get('total_candidates_evaluated', 0)}",
            f"    Shadow eligible:       {arbiter.get('shadow_eligible', 0)}",
            f"    Review candidates:     {arbiter.get('review_candidate', 0)}",
            f"    Do not trade:          {arbiter.get('do_not_trade', 0)}",
            f"    Psych alpha verdict:   {arbiter.get('psychology_alpha_best_candidate_verdict', 'N/A')}",
        ]
        if arb_best:
            arbiter_lines += [
                f"    Best: {arb_best['symbol']} {arb_best['timeframe']} {arb_best['direction']} "
                f"RR:1:{arb_best['rr']} Score:{arb_best['thesis_score']} "
                f"Trigger:{arb_best['trigger_status']} Source:{arb_best.get('candidate_source', '?')}",
            ]
        # Unified Candidate Bridge section (Phase 50)
        ub = arbiter.get("unified_bridge_candidates", {})
        if ub and ub.get("trigger_confirmed_count", 0) > 0:
            ub_list = ub.get("candidates", [])
            best_bridge = None
            for bc in ub_list:
                if bc.get("verdict") == "SHADOW_ELIGIBLE":
                    best_bridge = bc
                    break
            if not best_bridge and ub_list:
                best_bridge = max(ub_list, key=lambda x: (x.get("rr", 0), x.get("thesis_score", 0)))
            arbiter_lines += [
                "",
                "  UNIFIED CANDIDATE BRIDGE:",
                f"    Trigger confirmed candidates: {ub['trigger_confirmed_count']}",
                f"    Shadow eligible from trigger:  {ub['shadow_eligible_from_trigger']}",
                f"    Review candidate from trigger: {ub['review_candidate_from_trigger']}",
            ]
            if best_bridge:
                arbiter_lines += [
                    f"    Best bridge: {best_bridge['symbol']} {best_bridge['timeframe']} "
                    f"{best_bridge['direction']} RR:1:{best_bridge.get('rr', '?')} "
                    f"Score:{best_bridge.get('thesis_score', '?')}",
                    f"      Status: {best_bridge.get('verdict', 'DO_NOT_TRADE')}",
                ]
    else:
        arbiter_lines = ["", "  CANDIDATE ARBITER: MISSING (no report)", ""]

    # BingX shadow execution section
    shadow_lines = []
    if shadow:
        shadow_decision = shadow.get("decision", "N/A")
        has_intent = shadow.get("shadow_order_intent") is not None
        intent_source = shadow.get("shadow_order_intent", {}).get("source", "N/A") if has_intent else "N/A"
        shadow_lines = [
            "",
            "  BINGX SHADOW EXECUTION:",
            f"    Shadow Intent: {'GENERATED' if has_intent else 'NOT_GENERATED'}",
            f"    Shadow Decision: {shadow_decision}",
            f"    Intent Source: {intent_source}" if has_intent else "",
        ]
        if has_intent and shadow.get("shadow_order_intent"):
            si = shadow["shadow_order_intent"]
            shadow_lines += [
                f"    Symbol: {si.get('symbol', '?')} {si.get('side', '?')} "
                f"Entry:{si.get('entry', '?')} Stop:{si.get('stop_loss', '?')} "
                f"Target:{si.get('final_target', '?')} RR:1:{si.get('rr_final', '?')}",
                f"    Source: {si.get('source', 'N/A')}",
                f"    Candidate Source: {si.get('candidate_source', 'N/A')}",
                f"    Trigger Status: {si.get('trigger_status', 'N/A')}",
                f"    Thesis Score: {si.get('thesis_score', 'N/A')}",
            ]
        shr_reasons = shadow.get("reasons", [])
        if shr_reasons and shr_reasons != ["all gates passed"]:
            shadow_lines.append(f"    Reason: {'; '.join(shr_reasons)}")
    else:
        shadow_lines = ["", "  BINGX SHADOW EXECUTION: MISSING (no report)", ""]

    # BingX live micro preflight section
    preflight_lines = []
    if preflight:
        pf_dec = preflight.get("decision", "?")
        pf_sym = preflight.get("symbol", "N/A")
        pf_dir = preflight.get("direction", "N/A")
        pf_rr = preflight.get("rr_final", 0)
        pf_risk = preflight.get("risk_usdt", 0)
        pf_qty = preflight.get("quantity", 0)
        pf_checks = preflight.get("checks", {})
        passed_ct = sum(1 for v in pf_checks.values() if v)
        total_ct = len(pf_checks)
        preflight_lines = [
            "",
            "  LIVE MICRO PREFLIGHT:",
            f"    Decision:    {pf_dec}",
            f"    Symbol:      {pf_sym}",
            f"    Direction:   {pf_dir}",
            f"    RR:          {pf_rr}",
            f"    Risk:        {pf_risk} USDT",
            f"    Quantity:    {pf_qty}",
            f"    Checks:      {passed_ct}/{total_ct} passed",
            f"    Pass:        {'YES' if preflight.get('preflight_pass', False) else 'NO'}",
            f"    Message:     {preflight.get('message', 'N/A')}",
        ]
    else:
        preflight_lines = ["", "  LIVE MICRO PREFLIGHT: MISSING (no report)", ""]

    # BingX live micro execution section
    live_lines = []
    if live:
        lmode = live.get("execution_mode", "?")
        larmed = live.get("live_armed", False)
        lks = live.get("kill_switch", "OFF")
        ldec = live.get("decision", "?")
        lrisk = live.get("risk_usdt", 0)
        ldaily = live.get("environment", {}).get("MAX_DAILY_LOSS_USDT", 0)
        lreasons = live.get("reasons", [])
        live_lines = [
            "",
            "  BINGX LIVE MICRO EXECUTION:",
            f"    Live Executor Available: {'YES' if lmode == 'live_micro' else 'NO'}",
            f"    Live Armed: {'YES' if larmed else 'NO'}",
            f"    Kill Switch: {lks}",
            f"    Max Risk/Trade: {lrisk} USDT",
            f"    Max Daily Loss: {ldaily} USDT",
            f"    Latest Decision: {ldec}",
            f"    Latest Reason: {'; '.join(lreasons[:3])}" if lreasons else "    Latest Reason: N/A",
        ]
    else:
        live_lines = ["", "  BINGX LIVE MICRO EXECUTION: MISSING (no report)", ""]

    # Live position monitor section
    pos_lines = []
    if pos_mon:
        pf = pos_mon.get("position_found", False)
        pos_lines = [
            "",
            "  LIVE POSITION MONITOR:",
            f"    Open Position:     {'YES' if pf else 'NO'}",
            f"    Symbol:            {pos_mon.get('symbol') or 'N/A'}",
            f"    Entry Price:       {pos_mon.get('entry_price') or 'N/A'}",
            f"    Unrealized PnL:    {pos_mon.get('unrealized_pnl_usdt') or 'N/A'} USDT",
            f"    R Multiple:        {pos_mon.get('r_multiple') or 'N/A'}",
            f"    Stop Verified:     {'YES' if pos_mon.get('stop_verified') else 'NO'}",
            f"    Trade State:       {pos_mon.get('trade_state', 'N/A')}",
            f"    Emergency Status:  {pos_mon.get('emergency_status', 'OK')}",
            f"    Kill Switch:       {pos_mon.get('kill_switch', 'OFF')}",
        ]
        pos_warnings = pos_mon.get("warnings", [])
        if pos_warnings:
            pos_lines.append(f"    Warnings: {'; '.join(pos_warnings[:3])}")
    else:
        pos_lines = ["", "  LIVE POSITION MONITOR: MISSING (no report)", ""]

    # Hourly final status section
    hourly_lines = []
    if hourly:
        fa = hourly.get("final_action", "DO_NOTHING")
        fareason = hourly.get("action_reason", "")
        hourly_lines = [
            "",
            "  HOURLY FINAL STATUS:",
            f"    Final Action: {fa}",
            f"    Reason: {fareason}",
        ]
    else:
        hourly_lines = ["", "  HOURLY FINAL STATUS: MISSING (no hourly alert)", ""]

    sel_line = f"  TOP CANDIDATE: {selected_label}" if selected_label else "  TOP CANDIDATE: NONE"

    lines = [
        "=" * 60,
        "  DOCTOR DAILY PACKET",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  SYSTEM SAFE:    {'YES' if system_safe else 'NO'}",
        f"  LIVE DISABLED:  {'YES' if live_ok else 'NO'}",
        f"  PAPER DISABLED: {'YES' if paper_ok else 'NO'}",
        "",
        f"  EVIDENCE:       {trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days",
        "",
        "  Candidate Table:",
        "    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            "Config", "Direction", "RR T1", "RR T2", "Quality", "RR Gate", "Verdict", "Reason"),
        "    " + "-" * 88,
    ]
    lines += cand_lines
    lines += [
        "    " + "-" * 88,
        "",
        sel_line,
    ]
    if selected_label:
        lines += [
            "  SETUP LEVELS (selected):",
            f"    ENTRY:     {entry_str}",
            f"    STOP:      {stop_str}",
            f"    TARGET 1:  {t1_str}  (RR {rr1_str})",
            f"    TARGET 2:  {t2_str}  (RR {rr2_str})",
            "",
            "  RISK:",
            f"    POSITION SIZE: {pos_str}",
            f"    MAX LOSS IF STOP HIT: {loss_str} USDT",
        ]
    lines += tournament_lines
    lines += dux_lines
    lines += expanded_lines
    lines += alpha_lines
    lines += psych_lines
    lines += memory_lines
    lines += near_miss_lines
    lines += trigger_lines
    lines += arbiter_lines
    lines += shadow_lines
    lines += preflight_lines
    lines += live_lines
    lines += pos_lines
    lines += hourly_lines

    lines += [
        "",
        f"  FINAL DECISION: {decision}",
        f"  REASON: {'; '.join(reasons)}",
        "",
        "  WARNING: This system is not approved for live trading.",
        "  Manual trading is at user's own risk.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    report = {
        "mode": "doctor_daily_packet",
        "research_only": True,
        "timestamp": datetime.now().isoformat(),
        "system_safe": system_safe,
        "live_disabled": live_ok,
        "paper_disabled": paper_ok,
        "evidence": {
            "trades": trades,
            "days": days,
        },
        "candidates": candidates,
        "selected_candidate": selected_label,
        "selected_levels": selected_levels,
        "position_sizing": {
            "position_size": pos_sizing.get("position_size"),
            "risk_distance": pos_sizing.get("risk_distance"),
            "max_loss_if_hit": pos_sizing.get("max_loss_if_hit"),
        },
        "final_decision": decision,
        "reason": "; ".join(reasons),
        "disclaimer": "This system is not approved for live trading. Manual trading is at user's own risk.",
        "strategy_tournament": {
            "top_strategy": tournament.get("top_strategy") if tournament else None,
            "passing": tournament.get("passing", 0) if tournament else 0,
            "watching": tournament.get("watching", 0) if tournament else 0,
            "rejected": tournament.get("rejected", 0) if tournament else 0,
            "skipped": tournament.get("skipped", 0) if tournament else 0,
        } if tournament else None,
        "dux_pattern_engine": {
            "best_candidate": dux.get("best_candidate") if dux else None,
            "dux_scan_universe_size": dux.get("dux_scan_universe_size", dux.get("symbols_scanned", 0)) if dux else 0,
            "symbol_timeframes_scanned": dux.get("symbol_timeframes_scanned", 0) if dux else 0,
            "symbol_timeframes_attempted": dux.get("symbol_timeframes_attempted", 0) if dux else 0,
            "total_raw_contracts": dux.get("total_raw_contracts", dux.get("total_contracts", 0)) if dux else 0,
            "rr_gate_pass": dux.get("rr_gate_pass", 0) if dux else 0,
            "stats_pass": dux.get("stats_pass", 0) if dux else 0,
            "final_decision": dux.get("final_decision", "N/A") if dux else None,
            "tier_a_size": dux.get("tier_a_size", 0) if dux else 0,
            "tier_b_size": dux.get("tier_b_size", 0) if dux else 0,
            "tier_c_size": dux.get("tier_c_size", 0) if dux else 0,
            "failed_symbol_count": dux.get("failed_symbol_count", 0) if dux else 0,
            "api_error_count": dux.get("api_error_count", 0) if dux else 0,
            "scan_duration_seconds": dux.get("scan_duration_seconds", 0) if dux else 0,
        } if dux else None,
        "alpha_intelligence": {
            "best_candidate": alpha.get("best_candidate") if alpha else None,
            "alpha_score": alpha.get("best_candidate", {}).get("alpha_score") if alpha and alpha.get("best_candidate") else None,
            "rr_2": alpha.get("best_candidate", {}).get("rr_2") if alpha and alpha.get("best_candidate") else None,
            "elite": "YES" if alpha and alpha.get("best_candidate") and alpha["best_candidate"]["alpha_score"] >= 85 else "NO",
            "elite_candidates": alpha.get("alpha_elite_candidates", 0) if alpha else 0,
            "watch_candidates": alpha.get("alpha_watch_candidates", 0) if alpha else 0,
            "final_decision": alpha.get("final_decision", "N/A") if alpha else None,
        } if alpha else None,
        "market_psychology_alpha": {
            "best_candidate": {
                "symbol": psych.get("best_candidate", {}).get("symbol"),
                "pattern_name": psych.get("best_candidate", {}).get("pattern_name"),
                "psychology_score": psych.get("best_candidate", {}).get("psychology_score"),
                "psychology_thesis": psych.get("best_candidate", {}).get("psychology_thesis"),
                "rr_2": psych.get("best_candidate", {}).get("rr_2"),
                "verdict": psych.get("best_candidate", {}).get("verdict"),
            } if psych and psych.get("best_candidate") else None,
            "watch_candidates": psych.get("psychology_watch_candidates", 0) if psych else 0,
            "elite_candidates": psych.get("psychology_elite_candidates", 0) if psych else 0,
            "final_decision": psych.get("final_decision", "N/A") if psych else None,
        } if psych else None,
        "psychology_memory": {
            "scan_records_stored": memory.get("total_scan_records_stored", 0) if memory else None,
            "outcomes_evaluated": memory.get("total_outcomes_evaluated", 0) if memory else None,
            "pending_outcomes": memory.get("pending_outcomes", 0) if memory else None,
            "historical_edge_summary": memory.get("historical_edge_summary") if memory else None,
        } if memory else None,
        "trigger_watcher": {
            "candidates_watched": trigger_watcher.get("candidates_watched", 0) if trigger_watcher else 0,
            "active_watchlist_size": trigger_active.get("total_active", 0) if trigger_active else 0,
            "waiting": trigger_watcher.get("waiting_count", 0) if trigger_watcher else 0,
            "confirmed": trigger_watcher.get("confirmed_count", 0) if trigger_watcher else 0,
            "invalidated": trigger_watcher.get("invalidated_count", 0) if trigger_watcher else 0,
            "expired": trigger_watcher.get("expired_count", 0) if trigger_watcher else 0,
            "best_confirmed_candidate": trigger_watcher.get("best_confirmed_candidate") if trigger_watcher else None,
            "best_waiting_candidate": trigger_watcher.get("best_waiting_candidate") if trigger_watcher else None,
        } if trigger_watcher else None,
        "candidate_arbiter": {
            "total_candidates_evaluated": arbiter.get("total_candidates_evaluated", 0) if arbiter else 0,
            "shadow_eligible": arbiter.get("shadow_eligible", 0) if arbiter else 0,
            "review_candidate": arbiter.get("review_candidate", 0) if arbiter else 0,
            "do_not_trade": arbiter.get("do_not_trade", 0) if arbiter else 0,
            "has_shadow_eligible_candidates": arbiter.get("has_shadow_eligible_candidates", False) if arbiter else False,
            "psychology_alpha_best_candidate_verdict": arbiter.get("psychology_alpha_best_candidate_verdict") if arbiter else None,
            "best_candidate": arbiter.get("best_candidate") if arbiter else None,
        } if arbiter else None,
        "near_miss_diagnostics": {
            "signal_integrity": {
                "crypto_filter_pass": True,
                "excluded_non_crypto": near_miss.get("excluded_non_crypto", 0) if near_miss else 0,
                "deduplicated_candidates_removed": near_miss.get("deduplicated_candidates_removed", 0) if near_miss else 0,
                "validated_executable_before": near_miss.get("validated_executable_before", 0) if near_miss else 0,
                "validated_executable_after": near_miss.get("validated_executable_after", 0) if near_miss else 0,
                "executable_downgraded_count": near_miss.get("executable_downgraded_count", 0) if near_miss else 0,
            } if near_miss else None,
            "diagnostic_executable": near_miss.get("bucket_counts", {}).get("DIAGNOSTIC_EXECUTABLE", 0) if near_miss else 0,
            "trigger_confirmed": near_miss.get("bucket_counts", {}).get("TRIGGER_CONFIRMED", 0) if near_miss else 0,
            "arbiter_eligible": near_miss.get("bucket_counts", {}).get("ARBITER_ELIGIBLE", 0) if near_miss else 0,
            "watchlist_ready": near_miss.get("bucket_counts", {}).get("WATCHLIST_READY", 0) if near_miss else 0,
            "near_miss_rr": near_miss.get("bucket_counts", {}).get("NEAR_MISS_RR", 0) if near_miss else 0,
            "near_miss_psychology": near_miss.get("bucket_counts", {}).get("NEAR_MISS_PSYCHOLOGY", 0) if near_miss else 0,
            "raw_trap_detected": near_miss.get("bucket_counts", {}).get("RAW_TRAP_DETECTED", 0) if near_miss else 0,
            "top_rejection_reason": near_miss.get("top_rejection_reason") if near_miss else None,
            "best_watchlist_candidate": near_miss.get("best_watchlist_candidate") if near_miss else None,
            "excluded_non_crypto": near_miss.get("excluded_non_crypto", 0) if near_miss else 0,
            "crypto_contracts_scanned": near_miss.get("crypto_contracts_scanned", 0) if near_miss else 0,
            "directional_theses": near_miss.get("directional_theses_created", 0) if near_miss else 0,
            "long_theses": near_miss.get("long_theses", 0) if near_miss else 0,
            "short_theses": near_miss.get("short_theses", 0) if near_miss else 0,
        } if near_miss else None,
        "bingx_shadow_execution": {
            "shadow_intent": "GENERATED" if shadow and shadow.get("shadow_order_intent") else "NOT_GENERATED",
            "shadow_decision": shadow.get("decision", "N/A") if shadow else None,
            "reason": "; ".join(shadow.get("reasons", ["no shadow report"])) if shadow else None,
        } if shadow else None,
        "bingx_live_micro_execution": {
            "executor_available": live.get("execution_mode") == "live_micro" if live else False,
            "live_armed": live.get("live_armed", False) if live else False,
            "kill_switch": live.get("kill_switch", "OFF") if live else None,
            "max_risk_per_trade_usdt": live.get("risk_usdt", 0) if live else None,
            "max_daily_loss_usdt": live.get("environment", {}).get("MAX_DAILY_LOSS_USDT") if live else None,
            "latest_decision": live.get("decision") if live else None,
            "latest_reason": "; ".join(live.get("reasons", [])) if live else None,
        } if live else None,
        "live_position_monitor": {
            "position_found": pos_mon.get("position_found", False) if pos_mon else None,
            "symbol": pos_mon.get("symbol") if pos_mon else None,
            "entry_price": pos_mon.get("entry_price") if pos_mon else None,
            "unrealized_pnl_usdt": pos_mon.get("unrealized_pnl_usdt") if pos_mon else None,
            "r_multiple": pos_mon.get("r_multiple") if pos_mon else None,
            "stop_verified": pos_mon.get("stop_verified") if pos_mon else None,
            "trade_state": pos_mon.get("trade_state") if pos_mon else None,
            "emergency_status": pos_mon.get("emergency_status") if pos_mon else None,
            "warnings": pos_mon.get("warnings", []) if pos_mon else None,
        } if pos_mon else None,
        "hourly_final_status": {
            "final_action": hourly.get("final_action") if hourly else None,
            "reason": hourly.get("action_reason") if hourly else None,
        } if hourly else None,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
