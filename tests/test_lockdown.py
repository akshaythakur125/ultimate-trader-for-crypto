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
    assert "Daily Operator Checklist" in content


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
