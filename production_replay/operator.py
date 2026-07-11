"""Daily operator entrypoint.

Keeps the existing dry/paper pipeline usable by first refreshing market data
through live_scan, then running the BB paper pipeline summary.
"""

from __future__ import annotations

import argparse
from typing import Any

from production_replay import bb_paper_pipeline, live_scan


def operator_run(fast_daily: bool = True, config_labels: list[str] | None = None) -> dict[str, Any]:
    # ponytail: one sequential operator path; split fetch/report phases later if runtime grows too slow
    live_scan.main()
    pipeline_result = bb_paper_pipeline.run_pipeline()
    return {
        "fast_daily": fast_daily,
        "config_labels": config_labels or [],
        "pipeline_result": pipeline_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Keep the longer operator path.")
    parser.add_argument("--unlimited", action="store_true", help="Alias for the longer operator path.")
    args = parser.parse_args()

    fast_daily = not args.unlimited and not args.full
    operator_run(fast_daily=fast_daily)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
