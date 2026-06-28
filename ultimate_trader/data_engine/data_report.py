from typing import Optional

from ultimate_trader.data_engine.dataset_registry import DatasetInfo, DatasetRegistry, QualityStatus


class DataReport:
    @classmethod
    def generate(cls, registry: DatasetRegistry) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("DATASET QUALITY REPORT")
        lines.append("=" * 70)
        lines.append(f"{'Symbol':<12} {'TF':<6} {'Candles':<10} {'Days':<7} {'Start':<14} {'End':<14} {'Status':<22} {'Reason'}")
        lines.append("-" * 120)
        for d in sorted(registry.datasets, key=lambda x: (x.symbol, x.timeframe)):
            if d.quality == QualityStatus.GOOD:
                status = "GOOD"
            elif d.quality == QualityStatus.ACCEPTABLE_WITH_GAPS:
                status = "ACCEPTABLE"
            elif d.quality == QualityStatus.TOO_SHORT:
                status = "TOO_SHORT"
            else:
                status = "BAD"
            reason = d.reason[:40] if d.reason else ""
            lines.append(
                f"{d.symbol:<12} {d.timeframe:<6} {d.candle_count:<10} "
                f"{d.days_covered:<7.0f} {d.start_date:<14} {d.end_date:<14} "
                f"{status:<22} {reason}"
            )
        lines.append("-" * 120)
        good = sum(1 for d in registry.datasets if d.quality == QualityStatus.GOOD)
        acceptable = sum(1 for d in registry.datasets if d.quality == QualityStatus.ACCEPTABLE_WITH_GAPS)
        bad = sum(1 for d in registry.datasets if d.quality == QualityStatus.BAD)
        short = sum(1 for d in registry.datasets if d.quality == QualityStatus.TOO_SHORT)
        lines.append(f"Summary: {good} GOOD, {acceptable} ACCEPTABLE, {bad} BAD, {short} TOO_SHORT")
        lines.append("=" * 70)
        return "\n".join(lines)
