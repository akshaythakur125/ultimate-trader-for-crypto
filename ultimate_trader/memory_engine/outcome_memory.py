from collections import defaultdict

from ultimate_trader.memory_engine.market_case import MarketCase, OutcomeLabel


class OutcomeMemory:
    def calculate_win_rate(self, cases: list[MarketCase]) -> float:
        resolved = [
            c
            for c in cases
            if c.outcome_label in (OutcomeLabel.WIN, OutcomeLabel.LOSS)
        ]
        if not resolved:
            return 0.0
        wins = sum(1 for c in resolved if c.outcome_label == OutcomeLabel.WIN)
        return wins / len(resolved) * 100.0

    def calculate_average_rr(self, cases: list[MarketCase]) -> float:
        with_rr = [c for c in cases if c.realized_rr is not None]
        if not with_rr:
            return 0.0
        return sum(c.realized_rr for c in with_rr) / len(with_rr)

    def calculate_expectancy(self, cases: list[MarketCase]) -> float:
        with_rr = [c for c in cases if c.realized_rr is not None]
        if not with_rr:
            return 0.0
        wins = [
            c for c in with_rr if c.outcome_label == OutcomeLabel.WIN
        ]
        losses = [
            c for c in with_rr if c.outcome_label == OutcomeLabel.LOSS
        ]
        if not wins and not losses:
            return 0.0
        avg_win = (
            sum(c.realized_rr for c in wins) / len(wins) if wins else 0.0
        )
        avg_loss = (
            sum(abs(c.realized_rr) for c in losses) / len(losses)
            if losses
            else 0.0
        )
        win_rate = len(wins) / len(with_rr)
        return win_rate * avg_win - (1 - win_rate) * avg_loss

    def calculate_failure_rate(self, cases: list[MarketCase]) -> float:
        resolved = [
            c
            for c in cases
            if c.outcome_label in (OutcomeLabel.WIN, OutcomeLabel.LOSS)
        ]
        if not resolved:
            return 0.0
        losses = sum(1 for c in resolved if c.outcome_label == OutcomeLabel.LOSS)
        return losses / len(resolved) * 100.0

    def summarize_outcomes_by_regime(self, cases: list[MarketCase]) -> dict[str, dict]:
        by_regime: dict[str, list[MarketCase]] = defaultdict(list)
        for c in cases:
            by_regime[c.pattern_signature.regime_label].append(c)

        result: dict[str, dict] = {}
        for regime, group in by_regime.items():
            result[regime] = {
                "total": len(group),
                "wins": sum(
                    1 for c in group if c.outcome_label == OutcomeLabel.WIN
                ),
                "losses": sum(
                    1 for c in group if c.outcome_label == OutcomeLabel.LOSS
                ),
                "win_rate": round(self.calculate_win_rate(group), 1),
                "avg_rr": round(self.calculate_average_rr(group), 2),
            }
        return result

    def summarize_outcomes_by_symbol(
        self, cases: list[MarketCase]
    ) -> dict[str, dict]:
        by_sym: dict[str, list[MarketCase]] = defaultdict(list)
        for c in cases:
            by_sym[c.symbol].append(c)

        result: dict[str, dict] = {}
        for sym, group in by_sym.items():
            result[sym] = {
                "total": len(group),
                "win_rate": round(self.calculate_win_rate(group), 1),
                "avg_rr": round(self.calculate_average_rr(group), 2),
            }
        return result

    def summarize_outcomes_by_timeframe(
        self, cases: list[MarketCase]
    ) -> dict[str, dict]:
        by_tf: dict[str, list[MarketCase]] = defaultdict(list)
        for c in cases:
            by_tf[c.timeframe].append(c)

        result: dict[str, dict] = {}
        for tf, group in by_tf.items():
            result[tf] = {
                "total": len(group),
                "win_rate": round(self.calculate_win_rate(group), 1),
                "avg_rr": round(self.calculate_average_rr(group), 2),
            }
        return result
