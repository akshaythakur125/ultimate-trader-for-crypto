"""BB Paper Pipeline — simplified orchestrator.

Runs the BB bounce paper trading flow:
  1. bb_signal_generator  → scan candles for BB bounces
  2. bb_paper_dispatcher   → convert signals to candidates
  3. paper_rotation_engine → check eligibility, pick best
  4. paper_execution_ledger → open & monitor paper trades
  5. paper_outcome_validator → validate outcomes
"""
import json, os, subprocess, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_DIR = os.path.join(PROJECT_DIR, "deploy_results")
STATE_DIR = os.path.join(PROJECT_DIR, "runtime_state")


def _run_module(name: str, timeout: int = 60) -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", f"production_replay.{name}"],
            capture_output=True, text=True, timeout=timeout,
        )
        return True
    except Exception as e:
        print(f"  [{name}] FAILED: {e}")
        return False


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run_pipeline() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 60)
    print("  BB PAPER PIPELINE")
    print(f"  {ts}")
    print("=" * 60)

    # Stage 1: Signal generation
    print("\n  [1/5] BB Signal Generator...")
    ok1 = _run_module("bb_signal_generator")
    sig_report = _read_json(os.path.join(RESULTS_DIR, "bb_signal_report.json"))
    bb_count = sig_report.get("total_signals", 0)
    config_str = sig_report.get("bb_bounce", {}).get("config", "?")
    print(f"         {bb_count} signals (config: {config_str})")

    # Stage 2: Dispatcher
    print("\n  [2/5] BB Paper Dispatcher...")
    ok2 = _run_module("bb_paper_dispatcher")
    disp_report = _read_json(os.path.join(RESULTS_DIR, "bb_candidates.json"))
    cand_count = disp_report.get("candidates_produced", 0) if disp_report else 0
    print(f"         {cand_count} candidates")

    # Stage 3: Rotation engine
    print("\n  [3/5] Paper Rotation Engine...")
    ok3 = _run_module("paper_rotation_engine", timeout=30)
    rot_report = _read_json(os.path.join(RESULTS_DIR, "paper_rotation_report.json"))
    rc = rot_report.get("rotation_candidate") if rot_report else None
    if rc:
        print(f"         Selected: {rc.get('symbol')} {rc.get('direction')} RR:{rc.get('rr')}")
    else:
        print("         No candidate selected")

    # Stage 4: Execution
    print("\n  [4/5] Paper Execution Ledger...")
    ok4 = _run_module("paper_execution_ledger", timeout=30)
    exec_report = _read_json(os.path.join(RESULTS_DIR, "paper_execution_status.json"))
    pf = exec_report.get("portfolio", {}) if exec_report else {}
    active = pf.get("active_count", 0)
    max_t = pf.get("max_allowed", 3)
    print(f"         {active}/{max_t} trades active")

    # Stage 5: Outcome validation
    print("\n  [5/5] Paper Outcome Validator...")
    ok5 = _run_module("paper_outcome_validator", timeout=30)

    # Summary
    print("\n" + "=" * 60)
    print("  PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  Signals:    {bb_count}")
    print(f"  Candidates: {cand_count}")
    print(f"  Config:     {config_str}")
    print(f"  Trades:     {active}/{max_t} active")

    if active > 0:
        print("\n  Active Trades:")
        for t in pf.get("active_trades", []):
            print(f"    {t.get('symbol','?')} {t.get('side','?')} "
                  f"Entry:{t.get('entry','?')} "
                  f"P&L:{t.get('unrealized_pnl',0):.4f} "
                  f"{'FILLED' if t.get('entry_fill_check') else 'WAITING'}")

    print(f"\n  FINAL ACTION: PAPER_ONLY")
    print(f"  Live trading: NO")
    print()
    print("  Useful files:")
    print(f"    {RESULTS_DIR}/bb_signal_report.json")
    print(f"    {RESULTS_DIR}/paper_execution_status.json")
    print(f"    {STATE_DIR}/paper_portfolio.json")
    print(f"    {STATE_DIR}/paper_trades.jsonl")

    return {
        "timestamp": ts,
        "signals": bb_count,
        "candidates": cand_count,
        "active_trades": active,
        "max_trades": max_t,
        "config": config_str,
        "pipeline_ok": all([ok1, ok2, ok3, ok4, ok5]),
    }


if __name__ == "__main__":
    result = run_pipeline()
    sys.exit(0 if result.get("pipeline_ok") else 1)
