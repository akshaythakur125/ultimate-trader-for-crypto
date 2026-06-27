from collections import Counter, defaultdict

from ultimate_trader.memory_engine.market_case import MarketCase, OutcomeLabel
from ultimate_trader.memory_engine.pattern_signature import PatternSignature


class FailureMemory:
    def identify_common_failure_reasons(
        self, cases: list[MarketCase]
    ) -> list[tuple[str, int]]:
        failures = self._get_failures(cases)
        reasons = [
            c.failure_reason for c in failures if c.failure_reason
        ]
        return Counter(reasons).most_common()

    def identify_regimes_with_high_failure(
        self, cases: list[MarketCase]
    ) -> list[tuple[str, float]]:
        by_regime: dict[str, list[MarketCase]] = defaultdict(list)
        for c in cases:
            by_regime[c.pattern_signature.regime_label].append(c)

        failure_rates: list[tuple[str, float]] = []
        for regime, group in by_regime.items():
            resolved = [
                c
                for c in group
                if c.outcome_label in (OutcomeLabel.WIN, OutcomeLabel.LOSS)
            ]
            if not resolved:
                continue
            losses = sum(
                1 for c in resolved if c.outcome_label == OutcomeLabel.LOSS
            )
            failure_rates.append(
                (regime, round(losses / len(resolved) * 100, 1))
            )

        failure_rates.sort(key=lambda x: x[1], reverse=True)
        return failure_rates

    def identify_signatures_associated_with_losses(
        self, cases: list[MarketCase]
    ) -> list[tuple[str, int]]:
        losses = [
            c
            for c in cases
            if c.outcome_label == OutcomeLabel.LOSS
            and c.pattern_signature.regime_label
        ]
        regimes = [c.pattern_signature.regime_label for c in losses]
        return Counter(regimes).most_common()

    def generate_failure_warnings(
        self,
        current_signature: PatternSignature,
        similar_cases: list[MarketCase],
    ) -> list[str]:
        warnings: list[str] = []
        failures = [
            c for c in similar_cases if c.outcome_label == OutcomeLabel.LOSS
        ]
        if not failures:
            return warnings

        warning_pct = len(failures) / len(similar_cases) * 100
        if warning_pct > 50:
            warnings.append(
                f"WARNING: {warning_pct:.0f}% of similar cases were losses"
            )
        elif warning_pct > 30:
            warnings.append(
                f"CAUTION: {warning_pct:.0f}% of similar cases were losses"
            )

        reasons = Counter(
            c.failure_reason for c in failures if c.failure_reason
        )
        for reason, count in reasons.most_common(2):
            warnings.append(
                f"Common failure reason ({count}x): {reason}"
            )

        return warnings

    def _get_failures(self, cases: list[MarketCase]) -> list[MarketCase]:
        return [
            c
            for c in cases
            if c.outcome_label in (OutcomeLabel.LOSS, OutcomeLabel.BAD_NO_TRADE)
        ]
