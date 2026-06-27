from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import (
    AggressionBias,
    FlowWindow,
)


class AggressionAnalysisResult(BaseModel):
    aggression_bias: AggressionBias = AggressionBias.UNKNOWN
    buy_aggression_score: float = 0.0
    sell_aggression_score: float = 0.0
    large_trade_pressure: str = ""
    aggression_summary: str = ""


class AggressionAnalyzer:
    def __init__(
        self,
        aggression_threshold: float = 0.6,
        large_trade_threshold: float = 0.3,
    ):
        self.aggression_threshold = aggression_threshold
        self.large_trade_threshold = large_trade_threshold

    def analyze(self, window: FlowWindow) -> AggressionAnalysisResult:
        if window.trade_count == 0:
            return AggressionAnalysisResult(aggression_summary="No trade data available")

        total = window.total_buy_volume + window.total_sell_volume
        buy_ratio = window.total_buy_volume / total if total > 0 else 0.0
        sell_ratio = window.total_sell_volume / total if total > 0 else 0.0

        buy_aggro = round(buy_ratio * 100, 2)
        sell_aggro = round(sell_ratio * 100, 2)

        bias = self._determine_bias(buy_ratio, sell_ratio)
        pressure = self._evaluate_large_trade_pressure(window)
        summary = self._build_summary(bias, buy_aggro, sell_aggro, pressure, window)

        return AggressionAnalysisResult(
            aggression_bias=bias,
            buy_aggression_score=buy_aggro,
            sell_aggression_score=sell_aggro,
            large_trade_pressure=pressure,
            aggression_summary=summary,
        )

    def _determine_bias(self, buy_ratio: float, sell_ratio: float) -> AggressionBias:
        if buy_ratio > self.aggression_threshold:
            return AggressionBias.BUYER_AGGRESSION
        if sell_ratio > self.aggression_threshold:
            return AggressionBias.SELLER_AGGRESSION
        ratio_diff = abs(buy_ratio - sell_ratio)
        if ratio_diff < 0.1:
            return AggressionBias.BALANCED
        return AggressionBias.BUYER_AGGRESSION if buy_ratio > sell_ratio else AggressionBias.SELLER_AGGRESSION

    def _evaluate_large_trade_pressure(self, window: FlowWindow) -> str:
        if window.trade_count == 0:
            return "none"
        large_ratio = window.large_trade_count / window.trade_count
        if large_ratio > self.large_trade_threshold * 2:
            return "very_high"
        if large_ratio > self.large_trade_threshold:
            return "elevated"
        return "normal"

    def _build_summary(
        self,
        bias: AggressionBias,
        buy_score: float,
        sell_score: float,
        pressure: str,
        window: FlowWindow,
    ) -> str:
        parts = [f"bias={bias.value}", f"buy={buy_score:.0f}%", f"sell={sell_score:.0f}%"]
        if pressure != "normal":
            parts.append(f"large_trade_pressure={pressure}")
        parts.append(f"trades={window.trade_count}")
        return " | ".join(parts)
