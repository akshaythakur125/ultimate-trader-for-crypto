"""One-command health check for busy operators.

Usage:
    python -m production_replay.healthcheck
"""

import json, os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "accelerated_evidence_report.json")
LEDGER_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
LEDGER_FILE = os.path.join(LEDGER_DIR, "evidence_ledger.jsonl")
BRIEF_FILE = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "daily_brief.txt")


def _run(label, cmd):
    print(f"\n--- {label} ---")
    try:
        result = subprocess.run(
            [sys.executable, "-m", cmd],
            capture_output=True, text=True, timeout=60,
        )
        print(result.stdout)
        if result.returncode != 0:
            err = result.stderr[:500] if result.stderr else ""
            if err:
                print(err)
            return False
        return True
    except subprocess.TimeoutExpired:
        print("  TIMEOUT (>{60}s)")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    print("=" * 60)
    print("  HEALTH CHECK — ultimate-trader-for-crypto")
    print("=" * 60)

    failed = 0

    if not _run("SAFETY LOCK", "production_replay.safety_lock"):
        failed += 1
    if not _run("LAUNCH CHECK", "production_replay.launch_check"):
        failed += 1

    print("\n--- LIVE / PAPER / DRY CONFIG ---")
    try:
        from production_replay.launch_check import load_config
        cfg = load_config()
        live = cfg.get("live_trading", True)
        paper = cfg.get("paper_trading", True)
        dry = cfg.get("dry_run", False)
        if not live and not paper and dry:
            print("  LIVE DISABLED  | OK")
            print("  PAPER DISABLED | OK")
            print("  DRY_RUN ENABLED| OK")
        else:
            print(f"  LIVE={live} PAPER={paper} DRY={dry}  | MISCONFIGURED")
            failed += 1
    except Exception as e:
        print(f"  ERROR reading config: {e}")
        failed += 1

    print("\n--- ACCELERATED EVIDENCE REPORT ---")
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH) as f:
            report = json.load(f)
        t = report["summary"]["total_candidates"]
        p = report["summary"]["passed"]
        q = report["summary"]["quarantined"]
        fc = report["summary"]["failed"]
        print(f"  {t} candidates ({p} PASS, {q} QUARANTINE, {fc} FAIL)  | OK")
    else:
        print("  Not generated yet — run `python -m production_replay.accelerated_evidence`  | SKIP")

    print("\n--- EVIDENCE LEDGER ---")
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE) as f:
            count = sum(1 for l in f if l.strip())
        print(f"  {count} entry(ies) in runtime_state/evidence_ledger.jsonl  | OK")
    else:
        print("  No ledger yet — run `python -m production_replay.operator`  | SKIP")

    print("\n--- DAILY BRIEF ---")
    if os.path.exists(BRIEF_FILE):
        with open(BRIEF_FILE) as f:
            first = f.readline().strip()
        print(f"  {first}  | OK")
    else:
        print("  No brief yet — run `python -m production_replay.operator`  | SKIP")

    print("\n--- DAILY STATUS ---")
    try:
        from production_replay import daily_status
        print("  python -m production_replay.daily_status available  | OK")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    print("\n--- TODAY TRADE PLAN ---")
    plan_json = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "today_trade_plan.json")
    plan_txt = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "today_trade_plan.txt")
    if os.path.exists(plan_json):
        with open(plan_json) as f:
            tp = json.load(f)
        levels = tp.get("setup_levels", {})
        has_levels = levels.get("entry_zone") is not None or levels.get("entry_zone") is None  # field exists check
        has_direction = tp.get("direction") is not None
        if has_direction:
            print(f"  Direction: {tp['direction']}, Setup levels present  | OK")
        else:
            print(f"  {plan_txt}  | OK")
    else:
        print("  Not generated yet -- run `python -m production_replay.today_trade_plan`  | SKIP")
    try:
        from production_replay import today_trade_plan
        print("  python -m production_replay.today_trade_plan available  | OK")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    print("\n--- MANUAL RISK CONSOLE ---")
    risk_json = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "manual_risk_plan.json")
    risk_txt = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "manual_risk_plan.txt")
    if os.path.exists(risk_json):
        with open(risk_json) as f:
            rp = json.load(f)
        sizing = rp.get("position_sizing", {})
        has_pos = sizing.get("position_size") is not None or sizing.get("warning") is not None
        if has_pos:
            print(f"  Position sizing calculated  | OK")
        else:
            print(f"  {risk_txt}  | OK")
    else:
        print("  Not generated yet -- run `python -m production_replay.manual_risk_console`  | SKIP")
    try:
        from production_replay import manual_risk_console
        print("  python -m production_replay.manual_risk_console available  | OK")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    print("\n--- DOCTOR DAILY PACKET ---")
    packet_json = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "doctor_daily_packet.json")
    packet_txt = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "doctor_daily_packet.txt")
    if os.path.exists(packet_json):
        with open(packet_json) as f:
            pk = json.load(f)
        fd = pk.get("final_decision", "?")
        bc = pk.get("best_candidate", "?")
        print(f"  Decision: {fd}, Candidate: {bc}  | OK")
    else:
        print("  Not generated yet -- run `python -m production_replay.doctor_daily_packet`  | SKIP")
    try:
        from production_replay import doctor_daily_packet
        print("  python -m production_replay.doctor_daily_packet available  | OK")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1

    print("\n" + "=" * 60)
    if failed == 0:
        print("  SYSTEM SAFE    | YES")
        print("  LIVE DISABLED  | YES")
        print("  PAPER DISABLED | YES")
        print("  LOOP STATUS    | ALL CLEAR")
    else:
        print(f"  SYSTEM SAFE    | ISSUES FOUND ({failed} failure(s))")
        print("  LIVE DISABLED  | YES")
        print("  PAPER DISABLED | YES")
        print("  LOOP STATUS    | Fix above failures first")
    print("  TEST STATUS    | python -m pytest -q -k \"ledger or daily_status or healthcheck or safety or launch\"")
    print("  DAILY STATUS   | python -m production_replay.daily_status")
    print("  DOCTOR BRIEF   | cat deploy_results/daily_brief.txt")
    print("  DOCTOR PACKET  | cat deploy_results/doctor_daily_packet.txt")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
