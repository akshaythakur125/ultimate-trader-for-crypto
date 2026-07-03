"""Historical cache resolver — robust multi-path cache search.

Finds historical candle cache files by searching multiple possible locations
in priority order, using absolute project-root resolution (not CWD).

Offline research only — never enables live trading.
"""

import json, os, sys
from datetime import datetime

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
DIAG_JSON_PATH = os.path.join(RESULTS_DIR, "historical_replay_diagnostics.json")


def find_project_root() -> str:
    """Find the project root by walking up from this module's location.

    Looks for a directory containing 'runtime_state' as a subdirectory.
    Falls back to the directory containing 'production_replay'.
    """
    current = os.path.abspath(os.path.dirname(__file__))
    for _ in range(10):
        runtime = os.path.join(current, "runtime_state")
        if os.path.isdir(runtime):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    # Last resort: the production_replay parent
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def resolve_cache_dir(project_root: str | None = None) -> str:
    """Resolve the best available historical candle cache directory.

    Searches in this order, returning the first one that exists:
      1. <project_root>/runtime_state/candles_cache/
      2. <project_root>/runtime_state/historical_cache/
      3. ./runtime_state/candles_cache/
      4. ./runtime_state/historical_cache/

    Returns the path (may not exist — caller must check).
    """
    if project_root is None:
        project_root = find_project_root()

    candidates = [
        os.path.join(project_root, "runtime_state", "candles_cache"),
        os.path.join(project_root, "runtime_state", "historical_cache"),
        os.path.join(os.getcwd(), "runtime_state", "candles_cache"),
        os.path.join(os.getcwd(), "runtime_state", "historical_cache"),
    ]

    for path in candidates:
        if os.path.isdir(path):
            return path

    return candidates[0]  # return first candidate even if it doesn't exist


def count_cache_files(cache_dir: str) -> tuple[list[str], int]:
    """Count JSON cache files in a directory.

    Returns (file_names, count).
    Only counts files matching cache patterns.
    """
    if not os.path.isdir(cache_dir):
        return [], 0
    try:
        files = [
            f for f in os.listdir(cache_dir)
            if f.endswith(".json")
        ]
        files.sort()
        return files, len(files)
    except (OSError, PermissionError):
        return [], 0


def make_cache_diagnostics(project_root: str | None = None) -> dict:
    """Build a diagnostics dict for the cache resolution process.

    Returns dict with keys:
      - project_root
      - current_working_directory
      - selected_cache_dir
      - checked_directories (list)
      - cache_files_found (list of filenames)
      - cache_file_count
      - first_10_cache_files
      - cache_exists
      - timestamp
    """
    if project_root is None:
        project_root = find_project_root()

    cwd = os.getcwd()
    selected = resolve_cache_dir(project_root)

    candidates = [
        os.path.join(project_root, "runtime_state", "candles_cache"),
        os.path.join(project_root, "runtime_state", "historical_cache"),
        os.path.join(cwd, "runtime_state", "candles_cache"),
        os.path.join(cwd, "runtime_state", "historical_cache"),
    ]

    checked = []
    for path in candidates:
        checked.append({
            "path": path,
            "exists": os.path.isdir(path),
        })

    files, count = count_cache_files(selected)

    diag = {
        "project_root": project_root,
        "current_working_directory": cwd,
        "selected_cache_dir": selected,
        "checked_directories": checked,
        "cache_files_found": files[:10],  # first 10 only
        "cache_file_count": count,
        "cache_exists": os.path.isdir(selected),
        "timestamp": datetime.now().isoformat(),
    }
    return diag


def append_cache_diagnostics_to_report(report: dict) -> dict:
    """Merge cache diagnostics into an existing report dict."""
    cache_diag = make_cache_diagnostics()
    report["cache_resolver"] = cache_diag
    return report


def main():
    diag = make_cache_diagnostics()
    print("=== Historical Cache Resolver ===")
    print(f"  Project root:              {diag['project_root']}")
    print(f"  CWD:                       {diag['current_working_directory']}")
    print(f"  Selected cache dir:        {diag['selected_cache_dir']}")
    print(f"  Cache exists:              {diag['cache_exists']}")
    print(f"  Cache files found:         {diag['cache_file_count']}")
    for e in diag.get("checked_directories", []):
        status = "EXISTS" if e["exists"] else "MISSING"
        print(f"  Checked: {e['path']} [{status}]")
    if diag.get("cache_files_found"):
        print(f"  First files:              {diag['cache_files_found'][:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
