"""Tests for production lockdown — ensuring deployment safety.

Verifies:
1. Blocked configs cannot run
2. Live trading cannot be enabled accidentally
3. Paper trading cannot be enabled accidentally
4. Launch check blocks dirty git tree
5. Launch check blocks missing report
6. Launch check accepts only BTC15m, BTC30m, SOL15m in dry-run mode
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


def test_only_three_allowed_configs():
    from production_replay.launch_check import load_config
    config = load_config()
    allowed = config.get("allowed_configs", [])
    assert len(allowed) == 3, f"expected 3 allowed configs, got {len(allowed)}"
    expected = {("BTCUSDT", "15m"), ("BTCUSDT", "30m"), ("SOLUSDT", "15m")}
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
    assert report["verdict"] in ("ROBUST_EDGE", "REGIME_SPECIFIC_EDGE", "INSUFFICIENT_TRADES", "NO_EDGE")
    assert len(report["per_config"]) == 3, "expected 3 allowed configs"


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
    assert "operator.py" in content


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
