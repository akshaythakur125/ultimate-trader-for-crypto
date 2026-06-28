"""Phase 5 — Minimum evidence rule for forward test readiness.

Enforces three gates before live eligibility:

- Gate A: 100+ fresh unseen OOS trades from non-overlapping walk-forward windows.
- Gate B: 30+ calendar days of paper-trading results with acceptable metrics.
- Gate C: Cumulative peak-to-trough DD must not exceed emergency stop (12.0R).

Returns PASS / BLOCKED with reason.
"""

import json, os
from datetime import datetime, timedelta
from typing import Any

MIN_OOS_TRADES = 100
MIN_PAPER_DAYS = 30
MIN_PAPER_TRADES = 25  # minimum trades during paper period
MAX_ACCEPTABLE_DD_R = 10.0
MIN_ACCEPTABLE_PF = 1.2
MIN_ACCEPTABLE_WR = 35.0
EMERGENCY_STOP_R = 12.0


def check_minimum_evidence(
    result_path: str = "phase5_results/forward_test_result.json",
    paper_result_path: str | None = None,
    output_dir: str = "phase5_results",
) -> dict[str, Any]:
    """Check whether the frozen configuration meets minimum evidence
    requirements for live trading eligibility.

    Args:
        result_path: Path to forward_test_result.json (OOS trades).
        paper_result_path: Optional path to paper-trading result JSON.
        output_dir: Directory for report output.

    Returns:
        Dict with gate_a, gate_b, overall PASS/BLOCKED, and reason.
    """
    findings = []
    gates = {}

    # --- Gate A: Minimum OOS trades ---
    if not os.path.exists(result_path):
        gates["gate_a"] = {
            "status": "BLOCKED",
            "reason": f"forward test result not found at {result_path}",
        }
        findings.append("BLOCKED: no forward test data")
    else:
        with open(result_path) as f:
            data = json.load(f)

        if data.get("dry_run"):
            gates["gate_a"] = {
                "status": "BLOCKED",
                "reason": "forward test is in dry-run mode; no trades executed",
            }
            findings.append("BLOCKED: dry-run mode")
        else:
            trades = data.get("trade_diagnostics", [])
            oos_count = len(trades)
            windows = data.get("windows", 0)

            if oos_count >= MIN_OOS_TRADES and windows >= 3:
                gates["gate_a"] = {
                    "status": "PASS",
                    "oos_trades": oos_count,
                    "windows": windows,
                    "threshold": MIN_OOS_TRADES,
                }
                findings.append(f"PASS gate A: {oos_count} OOS trades >= {MIN_OOS_TRADES}")
            else:
                gates["gate_a"] = {
                    "status": "BLOCKED",
                    "oos_trades": oos_count,
                    "windows": windows,
                    "threshold": MIN_OOS_TRADES,
                    "reason": f"insufficient OOS trades ({oos_count} < {MIN_OOS_TRADES}) or windows ({windows} < 3)",
                }
                findings.append(f"BLOCKED gate A: {oos_count} OOS trades < {MIN_OOS_TRADES}")

    # --- Gate B: Paper-trading results ---
    if paper_result_path and os.path.exists(paper_result_path):
        with open(paper_result_path) as f:
            paper_data = json.load(f)

        paper_trades = paper_data.get("trade_diagnostics", [])
        paper_days = paper_data.get("calendar_days", 0)
        paper_pf = paper_data.get("profit_factor", 0)
        paper_wr = paper_data.get("win_rate", 0)
        paper_dd = paper_data.get("max_drawdown_r", 0)

        issues = []
        if paper_days < MIN_PAPER_DAYS:
            issues.append(f"only {paper_days} paper days < {MIN_PAPER_DAYS}")
        if len(paper_trades) < MIN_PAPER_TRADES:
            issues.append(f"only {len(paper_trades)} paper trades < {MIN_PAPER_TRADES}")
        if paper_dd > MAX_ACCEPTABLE_DD_R:
            issues.append(f"DD {paper_dd:.1f}R > {MAX_ACCEPTABLE_DD_R}R")
        if paper_pf < MIN_ACCEPTABLE_PF:
            issues.append(f"PF {paper_pf:.2f} < {MIN_ACCEPTABLE_PF}")
        if paper_wr < MIN_ACCEPTABLE_WR:
            issues.append(f"WR {paper_wr:.1f}% < {MIN_ACCEPTABLE_WR}%")

        if not issues:
            gates["gate_b"] = {
                "status": "PASS",
                "paper_days": paper_days,
                "paper_trades": len(paper_trades),
            }
            findings.append(f"PASS gate B: {paper_days} days, {len(paper_trades)} trades")
        else:
            gates["gate_b"] = {
                "status": "BLOCKED",
                "paper_days": paper_days,
                "paper_trades": len(paper_trades),
                "reason": "; ".join(issues),
            }
            findings.append(f"BLOCKED gate B: {'; '.join(issues)}")
    else:
        gates["gate_b"] = {
            "status": "BLOCKED",
            "reason": "paper-trading results not provided",
        }
        findings.append("BLOCKED gate B: no paper-trading data")

    # --- Gate C: Cumulative peak-to-trough DD must not exceed emergency stop ---
    with open(result_path) as f:
        data = json.load(f)
    cum_dd = data.get("cumulative_max_dd_r", 0)
    if cum_dd >= EMERGENCY_STOP_R:
        gates["gate_c"] = {
            "status": "BLOCKED",
            "cumulative_dd_r": cum_dd,
            "threshold": EMERGENCY_STOP_R,
            "reason": f"cumulative DD {cum_dd:.1f}R >= {EMERGENCY_STOP_R}R emergency stop",
        }
        findings.append(f"BLOCKED gate C: DD {cum_dd:.1f}R >= {EMERGENCY_STOP_R}R")
    else:
        gates["gate_c"] = {
            "status": "PASS",
            "cumulative_dd_r": cum_dd,
            "threshold": EMERGENCY_STOP_R,
        }
        findings.append(f"PASS gate C: DD {cum_dd:.1f}R < {EMERGENCY_STOP_R}R")

    # --- Overall verdict ---
    all_pass = all(g.get("status") == "PASS" for g in gates.values())
    overall = "PASS" if all_pass else "BLOCKED"

    report = {
        "status": overall,
        "timestamp": datetime.now().isoformat(),
        "gates": gates,
        "findings": findings,
    }

    path = os.path.join(output_dir, "minimum_evidence_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"[MINIMUM EVIDENCE] Overall: {overall}", flush=True)

    return report
