from ultimate_trader.strategy_engine.filters import ALL_FILTERS
from ultimate_trader.strategy_engine.models import FilterResult, StrategyConfig, StrategyContext


class ConfidenceScorer:
    def score(self, ctx: StrategyContext, config: StrategyConfig) -> tuple[dict[str, FilterResult], float]:
        results: dict[str, FilterResult] = {}
        total_weight = 0.0
        total_weighted = 0.0

        for filter_instance in ALL_FILTERS:
            result = filter_instance.evaluate(ctx, config)
            results[filter_instance.name] = result

            if result.data_available:
                total_weight += result.weight
                weighted = result.score * result.weight
                total_weighted += weighted
                result.weighted_score = round(weighted, 2)
            else:
                result.weighted_score = 0.0

        total_confidence = total_weighted / total_weight if total_weight > 0 else 0.0
        total_confidence = round(min(100.0, max(0.0, total_confidence)), 1)

        return results, total_confidence
