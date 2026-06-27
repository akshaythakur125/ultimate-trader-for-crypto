from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import (
    AbsorptionState,
    AggressionBias,
    FlowWindow,
)


class AbsorptionAnalysisResult(BaseModel):
    absorption_detected: bool = False
    absorption_type: AbsorptionState = AbsorptionState.NO_ABSORPTION
    absorbed_side: str = ""
    absorption_score: float = 0.0
    likely_passive_participant: str = ""
    absorption_summary: str = ""


class AbsorptionIntelligence:
    def __init__(
        self,
        absorption_ratio_threshold: float = 0.65,
        price_stuck_threshold: float = 0.1,
    ):
        self.absorption_ratio_threshold = absorption_ratio_threshold
        self.price_stuck_threshold = price_stuck_threshold
        self._history: list[dict] = []

    def analyze(
        self,
        window: FlowWindow,
        aggression_bias: AggressionBias,
        price_change_percent: float = 0.0,
    ) -> AbsorptionAnalysisResult:
        self._history.append({
            "window": window,
            "aggression": aggression_bias,
            "price_change": price_change_percent,
        })
        if len(self._history) > 20:
            self._history.pop(0)

        if window.trade_count < 3:
            return AbsorptionAnalysisResult(absorption_summary="Insufficient trade data")

        total = window.total_buy_volume + window.total_sell_volume
        if total == 0:
            return AbsorptionAnalysisResult(absorption_summary="No volume data")

        buy_ratio = window.total_buy_volume / total
        sell_ratio = window.total_sell_volume / total

        price_stuck = abs(price_change_percent) < self.price_stuck_threshold

        if buy_ratio > self.absorption_ratio_threshold and price_stuck:
            return AbsorptionAnalysisResult(
                absorption_detected=True,
                absorption_type=AbsorptionState.BUYING_ABSORBED,
                absorbed_side="buyers",
                absorption_score=round(buy_ratio * 100, 2),
                likely_passive_participant="institutional_seller",
                absorption_summary=(
                    f"Buying absorbed: {buy_ratio:.0%} buyer volume with "
                    f"{'no' if abs(price_change_percent) < 0.01 else 'minimal'} price advance"
                ),
            )

        if sell_ratio > self.absorption_ratio_threshold and price_stuck:
            return AbsorptionAnalysisResult(
                absorption_detected=True,
                absorption_type=AbsorptionState.SELLING_ABSORBED,
                absorbed_side="sellers",
                absorption_score=round(sell_ratio * 100, 2),
                likely_passive_participant="institutional_buyer",
                absorption_summary=(
                    f"Selling absorbed: {sell_ratio:.0%} seller volume with "
                    f"{'no' if abs(price_change_percent) < 0.01 else 'minimal'} price decline"
                ),
            )

        return AbsorptionAnalysisResult(
            absorption_detected=False,
            absorption_type=AbsorptionState.NO_ABSORPTION,
            absorption_summary="No absorption detected",
        )

    def reset(self):
        self._history.clear()
