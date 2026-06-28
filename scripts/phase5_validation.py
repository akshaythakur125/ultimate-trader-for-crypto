#!/usr/bin/env python3
"""Phase 5 — Production-readiness validation orchestrator.

Runs all 6 validation modules in sequence and produces a consolidated
phase5_report.json + phase5_report.txt.

Usage:
    python scripts/phase5_validation.py          # dry-run only (default)
    python scripts/phase5_validation.py --execute  # run forward test

Flags:
    --execute      Run the forward test (risk actual compute).
    --output DIR   Output directory (default: phase5_results).
"""

import argparse, json, os, sys, time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.forward_test_runner import run_forward_test
from production_replay.daily_report import generate_daily_report
from production_replay.risk_report import generate_risk_report
from production_replay.minimum_evidence_rule import check_minimum_evidence
from production_replay.kill_switch import check_kill_switch
from production_replay.audit_bias_check import audit_bias_check


def main():
    parser = argparse.ArgumentParser(
        description="Phase 5 — Production-readiness validation"
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Execute forward test (default: dry-run only)",
    )
    parser.add_argument(
        "--output", default="phase5_results",
        help="Output directory (default: phase5_results)",
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    start = time.time()

    print("=" * 70)
    print("PHASE 5 — PRODUCTION-READINESS VALIDATION")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)
    print()

    results = {}
    errors = []

    # Step 1: Audit bias check (no data needed)
    print("[1/6] Audit bias check...", flush=True)
    try:
        audit = audit_bias_check(output_dir=args.output)
        results["audit_bias_check"] = audit
        print(f"       Status: {audit['status']}", flush=True)
    except Exception as e:
        errors.append(f"audit_bias_check: {e}")
        print(f"       ERROR: {e}", flush=True)

    print()

    # Step 2: Forward test runner
    print("[2/6] Forward test runner...", flush=True)
    try:
        fwd = run_forward_test(
            dry_run=not args.execute,
            output_dir=args.output,
        )
        results["forward_test"] = fwd
        status = fwd.get("status", "error")
        print(f"       Status: {status}", flush=True)
    except Exception as e:
        errors.append(f"forward_test: {e}")
        print(f"       ERROR: {e}", flush=True)

    print()

    # Step 3: Daily report
    print("[3/6] Daily report...", flush=True)
    try:
        daily = generate_daily_report(
            result_path=os.path.join(args.output, "forward_test_result.json"),
            output_dir=args.output,
        )
        results["daily_report"] = daily
        print(f"       Status: {daily.get('status', 'error')}", flush=True)
    except Exception as e:
        errors.append(f"daily_report: {e}")
        print(f"       ERROR: {e}", flush=True)

    print()

    # Step 4: Risk report
    print("[4/6] Risk report...", flush=True)
    try:
        risk = generate_risk_report(
            result_path=os.path.join(args.output, "forward_test_result.json"),
            output_dir=args.output,
        )
        results["risk_report"] = risk
        print(f"       Status: {risk.get('status', 'error')}", flush=True)
        for w in risk.get("warnings", []):
            print(f"         WARNING: {w}", flush=True)
    except Exception as e:
        errors.append(f"risk_report: {e}")
        print(f"       ERROR: {e}", flush=True)

    print()

    # Step 5: Minimum evidence rule
    print("[5/6] Minimum evidence rule...", flush=True)
    try:
        evidence = check_minimum_evidence(
            result_path=os.path.join(args.output, "forward_test_result.json"),
            output_dir=args.output,
        )
        results["minimum_evidence"] = evidence
        print(f"       Status: {evidence.get('status', 'error')}", flush=True)
    except Exception as e:
        errors.append(f"minimum_evidence: {e}")
        print(f"       ERROR: {e}", flush=True)

    print()

    # Step 6: Kill-switch monitor
    print("[6/6] Kill-switch monitor...", flush=True)
    try:
        kill = check_kill_switch(
            result_path=os.path.join(args.output, "forward_test_result.json"),
            output_dir=args.output,
        )
        results["kill_switch"] = kill
        triggered = kill.get("kill_triggered", False)
        print(f"       Kill triggered: {triggered}", flush=True)
    except Exception as e:
        errors.append(f"kill_switch: {e}")
        print(f"       ERROR: {e}", flush=True)

    print()

    # Consolidated report
    elapsed = time.time() - start
    report = {
        "phase": "phase5",
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "execute_mode": args.execute,
        "results": results,
        "errors": errors,
        "all_steps_completed": len(errors) == 0,
    }

    json_path = os.path.join(args.output, "phase5_report.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    txt_path = os.path.join(args.output, "phase5_report.txt")
    with open(txt_path, "w") as f:
        f.write("PHASE 5 — PRODUCTION-READINESS VALIDATION REPORT\n")
        f.write(f"{'='*70}\n")
        f.write(f"Completed: {datetime.now().isoformat()}\n")
        f.write(f"Elapsed: {elapsed:.1f}s\n")
        f.write(f"Execute mode: {args.execute}\n")
        f.write(f"Errors: {len(errors)}\n")
        f.write(f"{'='*70}\n\n")

        for module_name, module_result in results.items():
            status = module_result.get("status", "unknown")
            f.write(f"[{module_name}] {status}\n")

        if errors:
            f.write(f"\nERRORS:\n")
            for e in errors:
                f.write(f"  - {e}\n")

        f.write(f"\n{'='*70}\n")
        f.write("END OF REPORT\n")

    print(f"\n{'='*70}", flush=True)
    print(f"PHASE 5 COMPLETE — {elapsed:.1f}s", flush=True)
    print(f"Report: {json_path}", flush=True)
    print(f"Text:   {txt_path}", flush=True)
    print(f"Errors: {len(errors)}", flush=True)
    print(f"{'='*70}", flush=True)


if __name__ == "__main__":
    main()
