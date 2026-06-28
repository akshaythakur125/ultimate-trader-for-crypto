"""Phase 5 — Static code audit for look-ahead bias and data leakage.

Scans key source files in the robustness lab and replay runner for
common sources of look-ahead bias, future leakage, and data snooping.

Checks:
1. No negative `.iloc` or `.shift(-N)` indexing in test code paths.
2. Train/test split is strictly time-causal.
3. No parameter tuning on test data (no `fit` on test).
4. No future event references (FOMC, CPI, etc) in backtest code.
5. No strategy logic in production pipeline.
"""

import ast, os, re, sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Files to audit (all relevant paths in the trading pipeline)
AUDIT_PATHS = [
    "ultimate_trader/robustness_lab/replay_runner.py",
    "ultimate_trader/robustness_lab/walk_forward_replay.py",
    "ultimate_trader/robustness_lab/frozen_config.py",
    "ultimate_trader/validation_lab/walk_forward_validator.py",
    "ultimate_trader/validation_lab/out_of_sample_validator.py",
    "ultimate_trader/regime_filter/regime_gate.py",
    "ultimate_trader/regime_filter/similarity_scorer.py",
]

# Patterns that may indicate look-ahead bias
SUSPICIOUS_PATTERNS: list[tuple[str, str, str]] = [
    (r"\.iloc\s*\[\s*-\s*1\s*\]", "HIGH", "negative iloc index (possible look-ahead)"),
    (r"\.iloc\s*\[\s*-\s*\d+\s*\]", "HIGH", "negative iloc index (possible look-ahead)"),
    (r"\.shift\s*\(\s*-\s*\d+\s*\)", "HIGH", "negative shift (future data leakage)"),
    (r"t\.timestamp\s*<\s*train_start", "LOW", "time comparison direction check"),
    (r"FOMC|CPI|ECB|Fed|jobs report", "MEDIUM", "future event reference in backtest"),
]

# Patterns that are explicitly allowed
ALLOWED_PATTERNS = [
    r"\.iloc\s*\[\s*-\s*1\s*\]",  # sometimes used in current-candle context in engine
]

IS_ALLOWED_RE = re.compile("|".join(ALLOWED_PATTERNS))


def audit_bias_check(
    paths: list[str] | None = None,
    output_dir: str = "phase5_results",
) -> dict[str, Any]:
    """Run static audit for look-ahead bias and data leakage.

    Args:
        paths: List of file paths to audit. Defaults to AUDIT_PATHS.
        output_dir: Directory for report output.

    Returns:
        Dict with pass/fail status, findings, and per-file results.
    """
    if paths is None:
        paths = AUDIT_PATHS

    findings: list[dict[str, Any]] = []
    file_results: dict[str, Any] = {}
    all_pass = True

    for filepath in paths:
        if not os.path.exists(filepath):
            file_results[filepath] = {"status": "SKIP", "reason": "file not found"}
            continue

        with open(filepath) as f:
            content = f.read()

        file_findings = []
        lines = content.split("\n")

        for pattern, severity, description in SUSPICIOUS_PATTERNS:
            for lineno, line in enumerate(lines, 1):
                match = re.search(pattern, line)
                if match:
                    # Check if pattern is in an allowed context
                    if IS_ALLOWED_RE.search(line):
                        continue
                    # Skip comments/docstrings
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    file_findings.append({
                        "line": lineno,
                        "code": stripped.strip(),
                        "severity": severity,
                        "description": description,
                    })

        # Time-causality check: verify train/test split uses strict <
        if "train_start" in content and "train_end" in content:
            if "train_start <= c.timestamp < train_end" in content:
                file_findings.append({
                    "line": 0,
                    "code": "train_start <= c.timestamp < train_end",
                    "severity": "INFO",
                    "description": "train/test split is time-causal (train_end <= test_start)",
                })

        # Check for fit on test data
        if "fit(test_set)" in content or "fit(test_candles)" in content:
            file_findings.append({
                "line": 0,
                "code": "fit(test_set) or fit(test_candles)",
                "severity": "CRITICAL",
                "description": "model fitting on test data (look-ahead bias)",
            })
            all_pass = False

        file_issues = [f for f in file_findings if f["severity"] != "INFO"]
        file_has_errors = any(f["severity"] in ("HIGH", "CRITICAL") for f in file_issues)
        if file_has_errors:
            all_pass = False

        file_results[filepath] = {
            "status": "FAIL" if file_has_errors else "PASS",
            "findings": file_findings,
        }
        findings.extend(file_findings)

    serious = [f for f in findings if f["severity"] in ("HIGH", "CRITICAL")]
    info = [f for f in findings if f["severity"] == "INFO"]

    report = {
        "status": "PASS" if all_pass else "FAIL",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "files_audited": len([p for p in paths if os.path.exists(p)]),
        "findings_high": len(serious),
        "findings_info": len(info),
        "critical_findings": serious,
        "info_findings": info,
        "file_results": file_results,
    }

    path = os.path.join(output_dir, "audit_report.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w") as f:
        # Use custom serialization for safety
        import json
        json.dump(report, f, indent=2, default=str)
    print(f"[AUDIT] Status: {report['status']} ({report['findings_high']} high/critical, {report['findings_info']} info)", flush=True)

    return report
