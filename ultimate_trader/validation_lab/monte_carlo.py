import random
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.validation_lab.performance_metrics import TradeResult


class MonteCarloResult(BaseModel):
    simulations_run: int = 0
    median_return_r: float = 0.0
    worst_case_drawdown_r: float = 0.0
    probability_of_ruin: float = 0.0
    confidence_interval_low: float = 0.0
    confidence_interval_high: float = 0.0
    passed: bool = False


class MonteCarloSimulator:
    def simulate(
        self,
        trades: list[TradeResult],
        num_simulations: int = 1000,
        ruin_threshold_r: float = -20.0,
    ) -> MonteCarloResult:
        if len(trades) < 5:
            return MonteCarloResult(passed=False)

        net_rs = [t.net_r for t in trades]
        total_returns = []
        all_drawdowns = []
        ruin_count = 0

        for _ in range(num_simulations):
            shuffled = random.sample(net_rs, len(net_rs))
            cumulative = 0.0
            peak = 0.0
            max_dd = 0.0
            for r in shuffled:
                cumulative += r
                peak = max(peak, cumulative)
                dd = peak - cumulative
                max_dd = max(max_dd, dd)
            total_returns.append(cumulative)
            all_drawdowns.append(max_dd)
            if cumulative < ruin_threshold_r:
                ruin_count += 1

        total_returns.sort()
        all_drawdowns.sort()

        median_return = total_returns[len(total_returns) // 2] if total_returns else 0.0
        worst_dd = all_drawdowns[-1] if all_drawdowns else 0.0
        prob_ruin = ruin_count / num_simulations if num_simulations > 0 else 0.0

        low_idx = int(num_simulations * 0.05)
        high_idx = int(num_simulations * 0.95)
        ci_low = total_returns[low_idx] if low_idx < len(total_returns) else 0.0
        ci_high = total_returns[high_idx] if high_idx < len(total_returns) else 0.0

        passed = prob_ruin < 0.05 and worst_dd < 15.0 and median_return > 0

        return MonteCarloResult(
            simulations_run=num_simulations,
            median_return_r=round(median_return, 4),
            worst_case_drawdown_r=round(worst_dd, 4),
            probability_of_ruin=round(prob_ruin, 4),
            confidence_interval_low=round(ci_low, 4),
            confidence_interval_high=round(ci_high, 4),
            passed=passed,
        )
