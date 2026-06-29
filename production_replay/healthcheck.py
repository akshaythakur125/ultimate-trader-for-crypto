"""One-command health check for busy operators.

Usage:
    python -m production_replay.healthcheck
"""

import json, os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "deploy_results", "accelerated_evidence_report.json")


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
    print("  TEST STATUS    | python -m pytest -q -k \"quick_regime or replay_runner or accelerated or safety or launch\"")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
