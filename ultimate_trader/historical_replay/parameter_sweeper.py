import copy
from typing import Any, Optional

from pydantic import BaseModel, Field

from ultimate_trader.historical_replay.models import ReplayConfig, ReplayTrade


class ParameterSweepResult(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    total_trades: int = 0
    win_rate: float = 0.0
    expectancy_r: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_r: float = 0.0
    trade_count: int = 0
    score: float = 0.0


class ParameterSweeperReport(BaseModel):
    results: list[ParameterSweepResult] = Field(default_factory=list)
    best_result: Optional[ParameterSweepResult] = None
    overfit_warning: bool = False
    overfit_reason: str = ""


class ParameterSweeper:
    def __init__(self) -> None:
        self._results: list[ParameterSweepResult] = []

    @property
    def results(self) -> list[ParameterSweepResult]:
        return list(self._results)

    def sweep(
        self,
        base_config: ReplayConfig,
        parameter_grid: dict[str, list[Any]],
        run_fn: Any,
    ) -> ParameterSweeperReport:
        self._results.clear()
        param_names = list(parameter_grid.keys())

        def _generate_combinations(idx: int, current: dict[str, Any]) -> None:
            if idx == len(param_names):
                config = copy.deepcopy(base_config)
                for k, v in current.items():
                    setattr(config, k, v)
                trades = run_fn(config)
                self._score_and_store(current, trades)
                return
            pname = param_names[idx]
            for pval in parameter_grid[pname]:
                current[pname] = pval
                _generate_combinations(idx + 1, current)

        _generate_combinations(0, {})

        return self._build_report()

    def _score_and_store(self, params: dict[str, Any], trades: list[ReplayTrade]) -> None:
        trade_count = len(trades)
        if trade_count == 0:
            self._results.append(ParameterSweepResult(params=dict(params)))
            return

        wins = [t for t in trades if t.net_r > 0]
        losses = [t for t in trades if t.net_r <= 0]
        win_rate = len(wins) / trade_count
        total_net_r = sum(t.net_r for t in trades)
        expectancy = total_net_r / trade_count if trade_count > 0 else 0.0

        total_win_r = sum(t.net_r for t in wins) if wins else 0.0
        total_loss_r = abs(sum(t.net_r for t in losses)) if losses else 0.0
        profit_factor = total_win_r / total_loss_r if total_loss_r > 0 else 0.0

        peak = 0.0
        drawdown = 0.0
        running = 0.0
        for t in trades:
            running += t.net_r
            if running > peak:
                peak = running
            dd = peak - running
            if dd > drawdown:
                drawdown = dd
        max_dd = drawdown

        score = expectancy * (win_rate * 5 + 1) - max_dd * 0.5
        if trade_count < 10:
            score *= 0.5

        self._results.append(ParameterSweepResult(
            params=dict(params),
            total_trades=len(trades),
            win_rate=round(win_rate, 4),
            expectancy_r=round(expectancy, 4),
            profit_factor=round(profit_factor, 4),
            max_drawdown_r=round(max_dd, 4),
            trade_count=trade_count,
            score=round(score, 4),
        ))

    def _build_report(self) -> ParameterSweeperReport:
        if not self._results:
            return ParameterSweeperReport()

        self._results.sort(key=lambda r: r.score, reverse=True)
        best = self._results[0]

        overfit = False
        reason = ""
        if len(self._results) >= 3:
            scores = [r.score for r in self._results[:5]]
            avg_top5 = sum(scores) / len(scores)
            if best.score > avg_top5 * 1.5:
                overfit = True
                reason = f"Best score {best.score:.2f} is >1.5x avg of top 5 ({avg_top5:.2f})"

        if best.trade_count < 10:
            overfit = True
            reason += f"; Only {best.trade_count} trades — high overfit risk"

        neighbor_scores = [
            r.score for r in self._results[1:4]
            if self._similar_params(r.params, best.params)
        ]
        if neighbor_scores:
            avg_neighbor = sum(neighbor_scores) / len(neighbor_scores)
            if best.score > avg_neighbor * 2:
                overfit = True
                reason += f"; Fragile — neighbor params score {avg_neighbor:.2f} vs best {best.score:.2f}"

        overfit_reason = reason.strip().strip(";") if overfit else ""

        return ParameterSweeperReport(
            results=self._results,
            best_result=best,
            overfit_warning=overfit,
            overfit_reason=overfit_reason,
        )

    def _similar_params(self, a: dict[str, Any], b: dict[str, Any]) -> bool:
        diffs = 0
        for k in a:
            if k in b:
                if isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)):
                    if abs(a[k] - b[k]) > 0:
                        diffs += 1
        return diffs <= 1
