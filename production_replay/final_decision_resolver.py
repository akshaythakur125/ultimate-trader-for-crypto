"""Final decision resolver — priority-based master gate for live trading decisions.

Priority order (highest to lowest):
  1. Evidence lock: live_allowed is False → EVIDENCE_BLOCKED
  2. Kill switch: ON → KILL_SWITCH_BLOCKED
  3. Execution mode: not live_micro → PAPER_ONLY (blocks live actions)
  4. Normal decision (pass through)

Usage:
    from production_replay.final_decision_resolver import resolve_final_action
    action, reason = resolve_final_action(evidence, kill_switch_on, execution_mode, base_action, base_reason)
"""


def resolve_final_action(
    evidence: dict | None,
    kill_switch_on: bool,
    execution_mode: str,
    base_action: str,
    base_reason: str,
) -> tuple[str, str]:
    """Apply priority-based override chain to determine final action.

    Args:
        evidence: Strategy evidence report dict (or None if not run).
        kill_switch_on: Whether kill switch file exists.
        execution_mode: Current execution mode (e.g. 'read_only', 'live_micro').
        base_action: Action from _determine_final_action (before overrides).
        base_reason: Reason from _determine_final_action.

    Returns:
        Tuple of (final_action, reason).
    """
    # Priority 1: Evidence lock — master gate
    if evidence is not None and not evidence.get("live_allowed", True):
        ev_verdict = evidence.get("evidence_verdict", "UNKNOWN")
        closed = evidence.get("closed_trades", 0)
        ev_reason = evidence.get("live_reason", "")
        if closed < 30:
            reason = f"evidence incomplete; {closed} closed trades; minimum 30 required"
        elif ev_reason:
            reason = f"evidence lock: {ev_reason} (verdict: {ev_verdict})"
        else:
            reason = f"evidence lock verdict: {ev_verdict}"
        return "EVIDENCE_BLOCKED", reason

    # Priority 2: Kill switch
    if kill_switch_on:
        return "KILL_SWITCH_BLOCKED", "kill switch is ON"

    # Priority 3: Execution mode — block live actions when not live_micro
    if execution_mode != "live_micro":
        if base_action in ("LIVE_ARMABLE", "LIVE_BLOCKED", "LIVE_READY", "LIVE_REVIEW_READY") or base_action.startswith("LIVE_"):
            return "PAPER_ONLY", f"execution mode is {execution_mode}, not live_micro"

    # Priority 4: Pass through
    return base_action, base_reason
