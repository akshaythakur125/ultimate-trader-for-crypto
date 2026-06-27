from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.validation_lab.performance_metrics import (
    PerformanceMetrics,
    TradeResult,
)


class ABTestResult(BaseModel):
    hypothesis_a: str
    hypothesis_b: str
    winner: Optional[str] = None
    performance_difference: dict = Field(default_factory=dict)
    simpler_model_preferred: bool = False
    conclusion: str = ""


class ABTestingEngine:
    def compare(
        self,
        trades_a: list[TradeResult],
        trades_b: list[TradeResult],
        name_a: str = "Hypothesis A",
        name_b: str = "Hypothesis B",
    ) -> ABTestResult:
        metrics_a = PerformanceMetrics.calculate(trades_a)
        metrics_b = PerformanceMetrics.calculate(trades_b)

        diff = {
            "expectancy_r_diff": round(metrics_a.expectancy_r - metrics_b.expectancy_r, 4),
            "win_rate_diff": round(metrics_a.win_rate - metrics_b.win_rate, 4),
            "profit_factor_diff": round(metrics_a.profit_factor - metrics_b.profit_factor, 4),
            "max_drawdown_r_diff": round(metrics_a.max_drawdown_r - metrics_b.max_drawdown_r, 4),
        }

        simpler_preferred = False
        if abs(diff["expectancy_r_diff"]) < 0.05:
            simpler_preferred = True

        winner = None
        if metrics_a.expectancy_r > metrics_b.expectancy_r + 0.05:
            winner = name_a
        elif metrics_b.expectancy_r > metrics_a.expectancy_r + 0.05:
            winner = name_b
        elif simpler_preferred:
            winner = name_a if len(trades_a) <= len(trades_b) else name_b

        if winner:
            conclusion = f"{winner} outperforms the alternative"
        else:
            conclusion = "No clear winner; performance is comparable"

        if simpler_preferred and winner is not None:
            conclusion += ", simpler model preferred"

        return ABTestResult(
            hypothesis_a=name_a,
            hypothesis_b=name_b,
            winner=winner,
            performance_difference=diff,
            simpler_model_preferred=simpler_preferred,
            conclusion=conclusion,
        )
