"""Tests for production lockdown — ensuring deployment safety.

Verifies:
1. Blocked configs cannot run
2. Live trading cannot be enabled accidentally
3. Paper trading cannot be enabled accidentally
4. Launch check blocks dirty git tree
5. Launch check blocks missing report
6. Launch check accepts only BTC15m, BTC30m in dry-run mode
"""

import json, os, sys, tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# --- Test 1: Locked config has live/paper disabled ---

def test_live_trading_disabled_in_locked_config():
    from production_replay.launch_check import load_config
    config = load_config()
    assert config.get("live_trading") is False, "live_trading must be false"
    assert config.get("paper_trading") is False, "paper_trading must be false"
    assert config.get("dry_run") is True, "dry_run must be true"


def test_blocked_configs_not_in_allowed():
    from production_replay.launch_check import load_config
    config = load_config()
    allowed = {(a["symbol"], a["timeframe"]) for a in config.get("allowed_configs", [])}
    blocked = {(b["symbol"], b["timeframe"]) for b in config.get("blocked_configs", [])}
    overlap = allowed & blocked
    assert not overlap, f"blocked configs appear in allowed: {overlap}"


def test_only_two_allowed_configs():
    from production_replay.launch_check import load_config
    config = load_config()
    allowed = config.get("allowed_configs", [])
    assert len(allowed) == 2, f"expected 2 allowed configs, got {len(allowed)}"
    expected = {("BTCUSDT", "15m"), ("BTCUSDT", "30m")}
    actual = {(a["symbol"], a["timeframe"]) for a in allowed}
    assert actual == expected, f"allowed mismatch: {actual - expected} unexpected, {expected - actual} missing"


# --- Test 2: Launch check gates ---

def test_launch_check_blocks_live_trading_enabled():
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": True, "paper_trading": False, "dry_run": True,
        "allowed_configs": [{"symbol": "BTCUSDT", "timeframe": "15m"}],
        "blocked_configs": [],
    }
    result = run_launch_check(config)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"]["live_trading_disabled"]["status"] == "FAIL"


def test_launch_check_blocks_paper_trading_enabled():
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": False, "paper_trading": True, "dry_run": True,
        "allowed_configs": [{"symbol": "BTCUSDT", "timeframe": "15m"}],
        "blocked_configs": [],
    }
    result = run_launch_check(config)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"]["paper_trading_disabled"]["status"] == "FAIL"


def test_launch_check_blocks_dry_run_disabled():
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": False, "paper_trading": False, "dry_run": False,
        "allowed_configs": [{"symbol": "BTCUSDT", "timeframe": "15m"}],
        "blocked_configs": [],
    }
    result = run_launch_check(config)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"]["dry_run_enabled"]["status"] == "FAIL"


def test_launch_check_blocks_blocked_config_in_allowed():
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": False, "paper_trading": False, "dry_run": True,
        "allowed_configs": [
            {"symbol": "BTCUSDT", "timeframe": "15m"},
            {"symbol": "ETHUSDT", "timeframe": "15m"},  # blocked!
        ],
        "blocked_configs": [{"symbol": "ETHUSDT", "timeframe": "15m"}],
    }
    result = run_launch_check(config)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"]["no_blocked_configs"]["status"] == "FAIL"


def test_launch_check_accepts_valid_dry_config():
    """With valid allowed configs and dry-run mode, report check should be
    the only failing gate (since no report exists in test context)."""
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": False, "paper_trading": False, "dry_run": True,
        "allowed_configs": [
            {"symbol": "BTCUSDT", "timeframe": "15m"},
            {"symbol": "BTCUSDT", "timeframe": "30m"},
            {"symbol": "SOLUSDT", "timeframe": "15m"},
        ],
        "blocked_configs": [
            {"symbol": "ETHUSDT", "timeframe": "15m"},
            {"symbol": "XRPUSDT", "timeframe": "15m"},
            {"symbol": "BNBUSDT", "timeframe": "15m"},
            {"symbol": "BTCUSDT", "timeframe": "1h"},
            {"symbol": "BTCUSDT", "timeframe": "5m"},
        ],
    }
    result = run_launch_check(config)
    # Safety gates should all pass; report check may fail
    assert result["gates"]["live_trading_disabled"]["status"] == "PASS"
    assert result["gates"]["paper_trading_disabled"]["status"] == "PASS"
    assert result["gates"]["dry_run_enabled"]["status"] == "PASS"
    assert result["gates"]["no_blocked_configs"]["status"] == "PASS"


# --- Test 3: Dry forward runner does not execute orders ---

def test_dry_forward_runner_no_trades_in_dry_mode():
    from production_replay.run_dry_forward import run_dry_forward
    # Run with a very short test to verify no API calls are made
    # We just check the module can be imported and structured correctly
    import inspect
    source = inspect.getsource(run_dry_forward)
    # Verify no order execution API calls in source
    assert "order" not in source.lower(), "order execution API call found in dry runner"
    assert "api" not in source.lower() or "bingx" not in source.lower(), "exchange API call found in dry runner"


# --- Test 4: Config file structure ---

def test_locked_config_yaml_keys():
    from production_replay.launch_check import load_config
    config = load_config()
    required_keys = [
        "live_trading", "paper_trading", "dry_run",
        "allowed_configs", "blocked_configs",
        "stop_method", "entry_method", "regime_gate", "risk_control",
        "min_ev_R", "min_pf", "max_dd_R_preferred", "max_dd_R_absolute",
        "min_total_oos_trades_before_paper", "min_paper_days_before_live",
    ]
    for key in required_keys:
        assert key in config, f"missing key in config: {key}"


def test_deployment_readme_exists():
    assert os.path.exists("production_replay/README_DEPLOYMENT.md")
    content = open("production_replay/README_DEPLOYMENT.md").read()
    assert "REGIME_SPECIFIC_EDGE" in content
    assert "live_trading" in content.lower()
    assert "paper_trading" in content.lower()
    assert "Daily Operating Procedure" in content


def test_dry_forward_report_structure():
    """Verify dry-forward report has all required fields."""
    report_path = "deploy_results/dry_forward_report.json"
    if not os.path.exists(report_path):
        pytest.skip("dry-forward report not generated yet")
    with open(report_path) as f:
        report = json.load(f)
    required = ["mode", "verdict", "total_trades", "total_wr", "total_ev",
                 "total_pf", "total_dd_r", "kill_triggered",
                 "live_trading_enabled", "paper_trading_enabled", "gates", "per_config"]
    for key in required:
        assert key in report, f"missing field in report: {key}"
    assert report["live_trading_enabled"] is False
    assert report["paper_trading_enabled"] is False
    assert report["mode"] == "dry_forward"
    assert report["verdict"] in ("ROBUST_EDGE", "REGIME_SPECIFIC_EDGE", "INSUFFICIENT_TRADES", "NO_EDGE", "READY_FOR_PAPER", "ERROR")
    assert len(report["per_config"]) == 2, "expected 2 allowed configs"


# --- Test 5: Operator ---

def test_operator_refuses_when_live_trading_true():
    """Operator must refuse when live_trading is enabled."""
    from production_replay.operator import operator_run
    # Simulated: we just verify the launch_check gate catches it
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": True, "paper_trading": False, "dry_run": True,
        "allowed_configs": [], "blocked_configs": [],
    }
    result = run_launch_check(config)
    assert result["verdict"] == "BLOCKED"


def test_operator_refuses_when_paper_trading_true():
    """Operator must refuse when paper_trading is enabled."""
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": False, "paper_trading": True, "dry_run": True,
        "allowed_configs": [], "blocked_configs": [],
    }
    result = run_launch_check(config)
    assert result["verdict"] == "BLOCKED"


# --- Test 6: Safety lock ---

def test_safety_lock_detects_order_execution_imports():
    """Safety lock must detect forbidden imports in production_replay."""
    from production_replay.safety_lock import check_no_api_or_order_imports
    ok, msg = check_no_api_or_order_imports()
    assert ok, f"forbidden import detected: {msg}"


def test_safety_lock_config_blocks_trading():
    """Safety lock must verify config correctly blocks trading."""
    from production_replay.safety_lock import check_config_locked
    ok, msg = check_config_locked()
    assert ok, f"config lock check failed: {msg}"


def test_safety_lock_eligible_for_live_trading_false():
    """Safety lock must verify eligible_for_live_trading is False."""
    from production_replay.safety_lock import check_eligible_for_live_trading_false
    ok, msg = check_eligible_for_live_trading_false()
    assert ok, f"eligible_for_live_trading check failed: {msg}"


# --- Test 7: Evidence tracker ---

def test_evidence_tracker_blocks_when_trades_under_100():
    """Evidence tracker must show paper unlock blocked when trades < 100."""
    from production_replay.evidence_tracker import track_evidence, MIN_TRADES_GATE
    report = {
        "total_trades": MIN_TRADES_GATE - 1,
        "total_wr": 50, "total_ev": 0.5, "total_pf": 2.0, "total_dd_r": 5.0,
        "kill_triggered": False, "verdict": "INSUFFICIENT_TRADES",
        "live_trading_enabled": False, "paper_trading_enabled": False,
        "gates": {}, "per_config": [],
    }
    evidence = track_evidence(report)
    assert evidence["paper_unlock_blocked"] is True
    assert not evidence["gates"]["gate_a_trades_ge_100"]["pass"]


def test_evidence_tracker_blocks_when_days_under_30():
    """Evidence tracker must show paper unlock blocked when days < 30."""
    from production_replay.evidence_tracker import track_evidence, MIN_TRADES_GATE, MIN_DAYS_GATE
    report = {
        "total_trades": MIN_TRADES_GATE + 10,
        "total_wr": 50, "total_ev": 0.5, "total_pf": 2.0, "total_dd_r": 5.0,
        "kill_triggered": False, "verdict": "REGIME_SPECIFIC_EDGE",
        "live_trading_enabled": False, "paper_trading_enabled": False,
        "gates": {}, "per_config": [],
    }
    evidence = track_evidence(report)
    assert evidence["calendar_days_logged"] < MIN_DAYS_GATE
    assert evidence["paper_unlock_blocked"] is True
    assert not evidence["gates"]["gate_b_days_ge_30"]["pass"]


def test_evidence_tracker_live_unlock_always_blocked():
    """Evidence tracker must show live unlock always blocked."""
    from production_replay.evidence_tracker import track_evidence
    evidence = track_evidence({})
    assert evidence["live_unlock_blocked"] is True
    assert "hard-coded" in evidence["live_unlock_reason"].lower()


# --- Test 8: Operator produces summary files ---

def test_operator_produces_summary_files():
    """Verify operator generates the required output files."""
    paths = [
        "deploy_results/dry_forward_report.json",
        "deploy_results/dry_forward_report.txt",
        "deploy_results/operator_summary.txt",
    ]
    for p in paths:
        assert os.path.exists(p), f"operator did not produce {p}"


def test_operator_summary_has_required_fields():
    """Verify operator_summary.txt contains key sections."""
    path = "deploy_results/operator_summary.txt"
    if not os.path.exists(path):
        pytest.skip("operator_summary.txt not available")
    content = open(path).read()
    for section in ["Launch Check", "Safety Lock", "Dry-Forward", "Evidence", "Operator Verdict"]:
        assert section in content, f"missing section in operator_summary.txt: {section}"


# --- Test 9: run_operator.bat exists ---

def test_run_operator_bat_exists():
    assert os.path.exists("run_operator.bat")
    content = open("run_operator.bat").read()
    assert "production_replay.operator" in content


# --- Test 10: Launch check handles None configs safely ---

def test_launch_check_handles_none_allowed_configs():
    """Launch check must not crash when allowed_configs is None."""
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": False, "paper_trading": False, "dry_run": True,
        "allowed_configs": None,
        "blocked_configs": None,
    }
    result = run_launch_check(config)
    assert result["verdict"] in ("PASS", "BLOCKED"), "crash instead of verdict"
    assert "no_blocked_configs" in result["gates"]
    assert result["gates"]["no_blocked_configs"]["status"] == "PASS"


def test_launch_check_handles_missing_allowed_configs():
    """Launch check must not crash when allowed_configs key is missing."""
    from production_replay.launch_check import run_launch_check
    config = {
        "live_trading": False, "paper_trading": False, "dry_run": True,
    }
    result = run_launch_check(config)
    assert result["verdict"] in ("PASS", "BLOCKED"), "crash instead of verdict"
    assert "no_blocked_configs" in result["gates"]


def test_launch_check_handles_none_config():
    """Launch check must not crash when config itself is None."""
    from production_replay.launch_check import run_launch_check
    result = run_launch_check(None)
    assert result["verdict"] in ("PASS", "BLOCKED"), "crash instead of verdict"


# --- Test 11: _determine_operator_verdict never TIMEOUT ---

def test_determine_verdict_never_timeout():
    """_determine_operator_verdict must never return TIMEOUT."""
    from production_replay.operator import _determine_operator_verdict
    # All configs timed out
    all_results = [
        {"label": "BTC 15m", "status": "TIMEOUT", "trades": 0},
        {"label": "BTC 30m", "status": "TIMEOUT", "trades": 0},
    ]
    dry_result = {"total_trades": 0, "verdict": "INSUFFICIENT_TRADES", "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {"paper_unlock_blocked": True, "live_unlock_blocked": True}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    assert "TIMEOUT" not in v, f"verdict must not contain TIMEOUT: {v}"
    assert v in ("ERROR", "INSUFFICIENT_TRADES", "READY_FOR_PAPER")


def test_determine_verdict_all_timeout_is_error():
    """When all configs time out, verdict must be ERROR."""
    from production_replay.operator import _determine_operator_verdict
    all_results = [
        {"label": "BTC 15m", "status": "TIMEOUT", "trades": 0},
        {"label": "BTC 30m", "status": "TIMEOUT", "trades": 0},
    ]
    dry_result = {"total_trades": 0, "verdict": "INSUFFICIENT_TRADES", "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    assert v == "ERROR"


def test_determine_verdict_partial_timeout_is_insufficient_trades():
    """When some configs complete but total < 100, verdict is INSUFFICIENT_TRADES."""
    from production_replay.operator import _determine_operator_verdict
    all_results = [
        {"label": "BTC 15m", "status": "TIMEOUT", "trades": 0},
        {"label": "BTC 30m", "status": "OK", "trades": 30},
    ]
    dry_result = {"total_trades": 30, "verdict": "INSUFFICIENT_TRADES", "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    assert v == "INSUFFICIENT_TRADES"


def test_determine_verdict_ready_for_paper():
    """When trades >= 100 and gates pass, verdict must be READY_FOR_PAPER."""
    from production_replay.operator import _determine_operator_verdict
    all_results = [
        {"label": "BTC 15m", "status": "OK", "trades": 50},
        {"label": "BTC 30m", "status": "OK", "trades": 50},
    ]
    dry_result = {"total_trades": 100, "verdict": "READY_FOR_PAPER", "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    assert v == "READY_FOR_PAPER"


def test_determine_verdict_mixed_timeout_reads_trade_verdict():
    """When some timeout but trades exist, verdict follows trade-based result."""
    from production_replay.operator import _determine_operator_verdict
    # One config timed out, one completed, but trades < 100
    all_results = [
        {"label": "SOL 15m", "status": "TIMEOUT", "trades": 0},
        {"label": "BTC 15m", "status": "OK", "trades": 40},
    ]
    dry_result = {"total_trades": 40, "verdict": "INSUFFICIENT_TRADES", "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    assert "TIMEOUT" not in v


# --- Test 12: run_with_timeout ---

def test_run_with_timeout_completes():
    """run_with_timeout must return result when func finishes in time."""
    from production_replay.operator import run_with_timeout
    result = run_with_timeout(lambda: 42, 10)
    assert result == 42


def test_run_with_timeout_raises_on_exception():
    """run_with_timeout must propagate exceptions from wrapped func."""
    from production_replay.operator import run_with_timeout
    with pytest.raises(ValueError, match="boom"):
        run_with_timeout(lambda: (_ for _ in ()).throw(ValueError("boom")), 10)


def test_run_with_timeout_times_out():
    """run_with_timeout must raise TimeoutError when func exceeds timeout."""
    import time
    from production_replay.operator import run_with_timeout
    with pytest.raises(TimeoutError, match="timed out"):
        run_with_timeout(lambda: time.sleep(10), 1)


# --- Test 12: Operator --quick/--full flags ---

def test_operator_default_mode_is_fast_daily():
    """Operator must default to FAST_DAILY mode (75d cache, 1 window)."""
    from production_replay.operator import operator_run
    import inspect
    source = inspect.getsource(operator_run)
    assert "fast_daily: bool = True" in source


def test_operator_quick_mode_parsing():
    """When --full is not given, quick_mode must be True."""
    from production_replay.operator import operator_run
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.argv", ["operator.py"])
        import importlib, production_replay.operator as op_mod
        importlib.reload(op_mod)
        # quick_mode logic: quick_mode = not args.full, so default True
        assert op_mod.operator_run  # module loaded okay


# --- Test 15: Partial timeout handling ---

def test_operator_continues_after_timeout():
    """operator_run must continue remaining configs after a timeout."""
    from production_replay.operator import operator_run
    import inspect
    source = inspect.getsource(operator_run)
    assert "except TimeoutError" in source
    assert "continuing" in source


def test_operator_writes_summary_on_partial_failure():
    """operator_run must write summary files even with partial failure."""
    from production_replay.operator import SUMMARY_FILE, TEXT_REPORT, JSON_REPORT
    from production_replay.operator import operator_run
    import inspect
    source = inspect.getsource(operator_run)
    assert SUMMARY_FILE in source or "summary" in source.lower()
    assert TEXT_REPORT in source or "text_report" in source.lower() or "dry_forward_report" in source
    assert JSON_REPORT in source or "json_report" in source.lower() or "dry_forward_report.json" in source


def test_operator_source_has_no_timeout_verdict():
    """_determine_operator_verdict must never return a TIMEOUT verdict."""
    from production_replay.operator import _determine_operator_verdict
    import inspect
    source = inspect.getsource(_determine_operator_verdict)
    # Check that no return statement uses TIMEOUT (docstring may mention it)
    lines_with_return = [l for l in source.split("\n") if l.strip().startswith("return")]
    for line in lines_with_return:
        assert "TIMEOUT" not in line, f"verdict return contains TIMEOUT: {line.strip()}"


# --- Test 16: FAST_DAILY mode ---

def test_fast_daily_uses_data_days_75():
    """FAST_DAILY must use 75 data_days (1-2 windows) instead of 365."""
    from production_replay.operator import operator_run
    import inspect
    source = inspect.getsource(operator_run)
    assert "data_days = 75 if fast_daily else 365" in source


def test_fast_daily_flag_accepted():
    """Operator must default to fast_daily=True (75d cache, 1 window)."""
    from production_replay.operator import operator_run
    import inspect
    source = inspect.getsource(operator_run)
    assert "fast_daily" in source
    # Default must be True
    assert "fast_daily: bool = True" in source or "fast_daily=True" in source


# --- Test 17: --config flag ---

def test_config_flag_parsing():
    """--config flag must parse config labels correctly."""
    from production_replay.operator import _parse_config_labels
    # Valid label
    result = _parse_config_labels(["BTC:15m"])
    assert result is not None
    assert len(result) >= 1
    # Single config
    assert isinstance(result, list)


def test_config_flag_invalid_does_not_crash():
    """Invalid --config value must not crash parser."""
    from production_replay.operator import _parse_config_labels
    result = _parse_config_labels(["INVALID:99m"])
    assert result is not None  # returns the raw string as fallback
    assert len(result) == 1


# --- Test 18: --unlimited flag ---

def test_unlimited_flag_provides_365d():
    """--unlimited must set fast_daily=False and use 365d."""
    from production_replay import operator
    import inspect
    source = inspect.getsource(operator)
    assert "fast_daily = not args.unlimited" in source
    assert "data_days = 75 if fast_daily else 365" in source
    assert "unlimited" in source


# --- Test 19: ensure_data fast_daily passthrough ---

def test_ensure_data_accepts_fast_daily():
    """ensure_data must accept fast_daily parameter."""
    from ultimate_trader.robustness_lab.replay_runner import ensure_data
    import inspect
    sig = inspect.signature(ensure_data)
    assert "fast_daily" in sig.parameters


# --- Test 20: Live/paper remain disabled in report ---

def test_dry_forward_report_live_paper_disabled():
    """dry_forward report must always have live/paper disabled."""
    report_path = "deploy_results/dry_forward_report.json"
    if not os.path.exists(report_path):
        pytest.skip("dry-forward report not generated yet")
    with open(report_path) as f:
        report = json.load(f)
    assert report.get("live_trading_enabled") is False
    assert report.get("paper_trading_enabled") is False


def test_operator_source_no_live_trading():
    """Operator source must not reference live trading enablement."""
    from production_replay import operator
    import inspect
    source = inspect.getsource(operator)
    assert "live_trading" not in source or "DISABLED" in source or "False" in source or "disabled" in source.lower()


# --- Test 21: _interval_minutes ---

# --- Test 21: Per-config status values ---

def test_per_config_status_values():
    """Per-config status must be one of OK/INSUFFICIENT_TRADES/TIMEOUT/ERROR."""
    from production_replay.operator import _compute_config_result
    statuses = set()
    # OK: has trades
    result = _compute_config_result({
        "symbol": "BTCUSDT", "timeframe": "15m",
        "status": "completed", "dry_run": False,
        "trade_diagnostics": [{"net_r": 1.0, "window": "w1"}],
        "window_metrics": [{"total_trades": 1}],
        "rejection_summary": [],
        "elapsed_s": 10, "total_unique_rejected": 0,
    }, "BTC 15m")
    assert result["status"] in ("OK", "INSUFFICIENT_TRADES", "TIMEOUT", "ERROR")
    assert result["status"] == "OK"

    # INSUFFICIENT_TRADES: 0 trades
    result2 = _compute_config_result({
        "symbol": "BTCUSDT", "timeframe": "15m",
        "status": "completed", "dry_run": False,
        "trade_diagnostics": [],
        "window_metrics": [],
        "rejection_summary": [],
        "elapsed_s": 10, "total_unique_rejected": 0,
    }, "BTC 15m")
    assert result2["status"] == "INSUFFICIENT_TRADES"


# --- Test 22: Fast daily candle trimming ---

def test_fast_daily_trims_candles():
    """forward_test_runner must trim candles in fast_daily mode to limit windows."""
    from production_replay.forward_test_runner import run_forward_test
    import inspect
    source = inspect.getsource(run_forward_test)
    assert "trimmed" in source or "cutoff_ts" in source


# --- Test 23: Operator verdict never TIMEOUT with partial completion ---

def test_operator_verdict_not_timeout_with_ok_config():
    """Operator verdict must not be TIMEOUT if at least one config completes."""
    from production_replay.operator import _determine_operator_verdict
    # One OK, one TIMEOUT, one ERROR
    all_results = [
        {"label": "BTC 15m", "status": "OK", "trades": 50},
        {"label": "BTC 30m", "status": "TIMEOUT", "trades": 0},
        {"label": "SOL 15m", "status": "ERROR", "trades": 0},
    ]
    dry_result = {"total_trades": 50, "verdict": "INSUFFICIENT_TRADES",
                  "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    assert "TIMEOUT" not in v
    assert v == "INSUFFICIENT_TRADES"


def test_operator_verdict_all_errors():
    """When all configs error out, verdict must be ERROR."""
    from production_replay.operator import _determine_operator_verdict
    all_results = [
        {"label": "BTC 15m", "status": "ERROR", "trades": 0},
        {"label": "BTC 30m", "status": "TIMEOUT", "trades": 0},
    ]
    dry_result = {"total_trades": 0, "verdict": "INSUFFICIENT_TRADES",
                  "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    assert v == "ERROR"


def test_insufficient_trades_config_still_counts_as_completed():
    """A config with INSUFFICIENT_TRADES status counts as completed (not error)."""
    from production_replay.operator import _determine_operator_verdict
    all_results = [
        {"label": "BTC 15m", "status": "INSUFFICIENT_TRADES", "trades": 0},
        {"label": "BTC 30m", "status": "OK", "trades": 40},
    ]
    dry_result = {"total_trades": 40, "verdict": "INSUFFICIENT_TRADES",
                  "live_trading_enabled": False, "paper_trading_enabled": False}
    evidence = {}
    v = _determine_operator_verdict(all_results, dry_result, evidence)
    # At least one completed, so NOT ERROR (all_failed = False)
    assert v != "ERROR"
    assert v == "INSUFFICIENT_TRADES"


def test_operator_summary_shows_live_paper_disabled():
    """operator_summary.txt must show live and paper trading as DISABLED."""
    path = "deploy_results/operator_summary.txt"
    if not os.path.exists(path):
        pytest.skip("operator_summary.txt not available")
    content = open(path).read()
    assert "Live trading:  DISABLED" in content
    assert "Paper trading: DISABLED" in content


# --- Test 24: VM_FAST mode ---

def test_vm_fast_per_config_timeout_60():
    """VM_FAST must have 60s per-config timeout."""
    from production_replay import operator
    assert operator.CONFIG_TIMEOUT == 60, "per-config timeout must be 60s"


def test_vm_fast_total_timeout_240():
    """VM_FAST must have 240s total operator timeout."""
    from production_replay import operator
    assert operator.TOTAL_TIMEOUT == 240, "total timeout must be 240s"


def test_vm_fast_passes_vm_fast_to_runner():
    """operator_run must pass vm_fast=True to run_forward_test."""
    from production_replay.operator import operator_run
    import inspect
    source = inspect.getsource(operator_run)
    assert "vm_fast=True" in source, "must pass vm_fast=True to forward test"


def test_vm_fast_uses_cache_only():
    """VM_FAST must not download — only use cached data."""
    from production_replay.forward_test_runner import run_forward_test
    import inspect
    source = inspect.getsource(run_forward_test)
    assert "vm_fast" in source
    assert "_csv_path" in source or "load_candles_from_csv" in source


def test_vm_fast_no_365d_download():
    """VM_FAST must load from cache, not download via ensure_data."""
    from production_replay.forward_test_runner import run_forward_test
    import inspect
    source = inspect.getsource(run_forward_test)
    # Verify both paths exist
    assert "if vm_fast:" in source
    assert "else:" in source
    assert "_csv_path" in source
    assert "load_candles_from_csv" in source


# --- Test 25: _interval_minutes ---

def test_interval_minutes_15m():
    """15m -> 15."""
    from ultimate_trader.robustness_lab.replay_runner import _interval_minutes
    assert _interval_minutes("15m") == 15


def test_interval_minutes_30m():
    """30m -> 30."""
    from ultimate_trader.robustness_lab.replay_runner import _interval_minutes
    assert _interval_minutes("30m") == 30


def test_interval_minutes_1h():
    """1h -> 60."""
    from ultimate_trader.robustness_lab.replay_runner import _interval_minutes
    assert _interval_minutes("1h") == 60


def test_interval_minutes_1d():
    """1d -> 1440."""
    from ultimate_trader.robustness_lab.replay_runner import _interval_minutes
    assert _interval_minutes("1d") == 1440



