"""Safety lock — verifies all deployment safety locks are engaged.

Checks:
1. live_trading is false in config_locked.yaml
2. paper_trading is false in config_locked.yaml
3. dry_run is true in config_locked.yaml
4. eligible_for_live_trading is false in validation_gate.py
5. no API/order execution imports exist in production_replay/
6. config_locked.yaml still hard-blocks trading
"""

import ast, os, sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.launch_check import load_config

CONFIG_PATH = "production_replay/config_locked.yaml"
VALIDATION_GATE_PATH = "ultimate_trader/validation_lab/validation_gate.py"
PRODUCTION_REPLAY_DIR = "production_replay"

FORBIDDEN_IMPORTS = [
    "bingx", "ccxt", "exchange", "order", "trade_executor",
    "api_key", "api_secret", "websocket", "stream",
]


def check_config_locked() -> tuple[bool, str]:
    config = load_config()
    if not config:
        return False, "could not load config_locked.yaml"
    lt = config.get("live_trading", None)
    pt = config.get("paper_trading", None)
    dr = config.get("dry_run", None)
    if lt is not False:
        return False, f"live_trading is {lt}, expected false"
    if pt is not False:
        return False, f"paper_trading is {pt}, expected false"
    if dr is not True:
        return False, f"dry_run is {dr}, expected true"
    return True, "config_locked.yaml correctly blocks trading"


def check_eligible_for_live_trading_false() -> tuple[bool, str]:
    if not os.path.exists(VALIDATION_GATE_PATH):
        return False, f"validation_gate.py not found at {VALIDATION_GATE_PATH}"
    with open(VALIDATION_GATE_PATH) as f:
        source = f.read()
    if "eligible_for_live_trading=False" in source.replace(" ", ""):
        return True, "eligible_for_live_trading hard-coded to False"
    return False, "eligible_for_live_trading is not hard-coded to False!"


def check_no_api_or_order_imports() -> tuple[bool, str]:
    issues = []
    replay_dir = Path(PRODUCTION_REPLAY_DIR)
    for pyfile in replay_dir.rglob("*.py"):
        try:
            with open(pyfile) as f:
                source = f.read()
        except Exception:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORTS:
                        if forbidden in alias.name.lower():
                            issues.append(f"{pyfile.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in FORBIDDEN_IMPORTS:
                        if forbidden in node.module.lower():
                            issues.append(f"{pyfile.name}: from {node.module} import ...")
    if issues:
        return False, f"forbidden imports found: {', '.join(issues)}"
    return True, "no API/order execution imports in production_replay/"


def run_safety_lock() -> dict[str, Any]:
    checks = {}

    ok1, msg1 = check_config_locked()
    checks["config_locked"] = {"pass": ok1, "detail": msg1}

    ok2, msg2 = check_eligible_for_live_trading_false()
    checks["eligible_for_live_trading_false"] = {"pass": ok2, "detail": msg2}

    ok3, msg3 = check_no_api_or_order_imports()
    checks["no_api_or_order_imports"] = {"pass": ok3, "detail": msg3}

    all_ok = all(c["pass"] for c in checks.values())
    result = {
        "pass": all_ok,
        "checks": checks,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }

    # Print
    print("=" * 72)
    print("  SAFETY LOCK")
    print("=" * 72)
    for name, c in checks.items():
        print(f"  {'PASS' if c['pass'] else 'FAIL':6s} | {name:<40s} {c['detail']}")
    print("-" * 72)
    print(f"  Verdict: {'ALL LOCKS ENGAGED' if all_ok else 'LOCK COMPROMISED'}")
    print("=" * 72)
    return result


if __name__ == "__main__":
    result = run_safety_lock()
    sys.exit(0 if result["pass"] else 1)
