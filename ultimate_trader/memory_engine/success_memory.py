from collections import Counter, defaultdict

from ultimate_trader.memory_engine.market_case import MarketCase, OutcomeLabel
from ultimate_trader.memory_engine.pattern_signature import PatternSignature


class SuccessMemory:
    def identify_common_success_reasons(
        self, cases: list[MarketCase]
    ) -> list[tuple[str, int]]:
        successes = self._get_successes(cases)
        reasons = [
            c.success_reason for c in successes if c.success_reason
        ]
        return Counter(reasons).most_common()

    def identify_regimes_with_high_success(
        self, cases: list[MarketCase]
    ) -> list[tuple[str, float]]:
        by_regime: dict[str, list[MarketCase]] = defaultdict(list)
        for c in cases:
            by_regime[c.pattern_signature.regime_label].append(c)

        success_rates: list[tuple[str, float]] = []
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
            success_rates.append(
                (regime, round(wins / len(resolved) * 100, 1))
            )

        success_rates.sort(key=lambda x: x[1], reverse=True)
        return success_rates

    def identify_signatures_associated_with_wins(
        self, cases: list[MarketCase]
    ) -> list[tuple[str, int]]:
        wins = [
            c
            for c in cases
            if c.outcome_label == OutcomeLabel.WIN
            and c.pattern_signature.regime_label
        ]
        regimes = [c.pattern_signature.regime_label for c in wins]
        return Counter(regimes).most_common()

    def generate_success_support(
        self,
        current_signature: PatternSignature,
        similar_cases: list[MarketCase],
    ) -> list[str]:
        support: list[str] = []
        successes = [
            c for c in similar_cases if c.outcome_label == OutcomeLabel.WIN
        ]
        if not successes:
            return support

        support_pct = len(successes) / len(similar_cases) * 100
        if support_pct > 60:
            support.append(
                f"STRONG: {support_pct:.0f}% of similar cases were wins"
            )
        elif support_pct > 40:
            support.append(
                f"FAVORABLE: {support_pct:.0f}% of similar cases were wins"
            )

        avg_rr = sum(
            c.realized_rr for c in successes if c.realized_rr is not None
        )
        rr_count = sum(1 for c in successes if c.realized_rr is not None)
        if rr_count > 0:
            avg = round(avg_rr / rr_count, 2)
            support.append(f"Avg R:R in similar wins: {avg}")

        return support

    def _get_successes(self, cases: list[MarketCase]) -> list[MarketCase]:
        return [c for c in cases if c.outcome_label == OutcomeLabel.WIN]
