from collections import defaultdict

from ultimate_trader.memory_engine.market_case import MarketCase, OutcomeLabel


class RegimeMemory:
    def __init__(self) -> None:
        self.regime_success_map: dict[str, float] = {}
        self.regime_failure_map: dict[str, float] = {}

    def build_from_cases(self, cases: list[MarketCase]) -> None:
        by_regime: dict[str, list[MarketCase]] = defaultdict(list)
        for c in cases:
            by_regime[c.pattern_signature.regime_label].append(c)

        for regime, group in by_regime.items():
            resolved = [
                c
                for c in group
                if c.outcome_label in (OutcomeLabel.WIN, OutcomeLabel.LOSS)
            ]
            if not resolved:
                continue
            wins = sum(
                1 for c in resolved if c.outcome_label == OutcomeLabel.WIN
            )
            losses = sum(
                1 for c in resolved if c.outcome_label == OutcomeLabel.LOSS
            )
            self.regime_success_map[regime] = round(
                wins / len(resolved) * 100, 1
            )
            self.regime_failure_map[regime] = round(
                losses / len(resolved) * 100, 1
            )

    def get_best_regimes(self, top_n: int = 3) -> list[tuple[str, float]]:
        sorted_regimes = sorted(
            self.regime_success_map.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_regimes[:top_n]

    def get_dangerous_regimes(self, top_n: int = 3) -> list[tuple[str, float]]:
        sorted_regimes = sorted(
            self.regime_failure_map.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_regimes[:top_n]

    def get_regime_warning(self, regime_label: str) -> str:
        failure_rate = self.regime_failure_map.get(regime_label, 0.0)
        if failure_rate > 60:
            return (
                f"DANGEROUS: {regime_label} has {failure_rate:.0f}% "
                f"historical failure rate"
            )
        if failure_rate > 40:
            return (
                f"CAUTION: {regime_label} has {failure_rate:.0f}% "
                f"historical failure rate"
            )
        if failure_rate > 0:
            return (
                f"MODERATE: {regime_label} has {failure_rate:.0f}% "
                f"historical failure rate"
            )
        return f"UNKNOWN: no historical data for {regime_label}"
