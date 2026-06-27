from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import (
    DeltaDivergenceType,
    FlowWindow,
)


class DeltaDivergenceResult(BaseModel):
    divergence_detected: bool = False
    divergence_type: DeltaDivergenceType = DeltaDivergenceType.NO_DIVERGENCE
    divergence_strength: str = ""
    interpretation: str = ""


class DeltaDivergenceDetector:
    def __init__(self, history_length: int = 10):
        self.history_length = history_length
        self._price_history: list[float] = []
        self._delta_history: list[float] = []

    def analyze(self, window: FlowWindow, current_price: float) -> DeltaDivergenceResult:
        self._price_history.append(current_price)
        self._delta_history.append(window.cumulative_delta)
        if len(self._price_history) > self.history_length:
            self._price_history.pop(0)
        if len(self._delta_history) > self.history_length:
            self._delta_history.pop(0)

        if len(self._price_history) < 3:
            return DeltaDivergenceResult(interpretation="Insufficient history for divergence detection")

        bull_div = self._check_bullish_divergence()
        bear_div = self._check_bearish_divergence()

        if bull_div and bear_div:
            return DeltaDivergenceResult(
                divergence_detected=False,
                divergence_type=DeltaDivergenceType.NO_DIVERGENCE,
                interpretation="Conflicting divergence signals",
            )

        if bull_div:
            strength = self._compute_strength()
            return DeltaDivergenceResult(
                divergence_detected=True,
                divergence_type=DeltaDivergenceType.BULLISH_DIVERGENCE,
                divergence_strength=strength,
                interpretation=(
                    f"Price making lower lows but delta making higher lows — "
                    f"{strength} bullish divergence, selling pressure weakening"
                ),
            )

        if bear_div:
            strength = self._compute_strength()
            return DeltaDivergenceResult(
                divergence_detected=True,
                divergence_type=DeltaDivergenceType.BEARISH_DIVERGENCE,
                divergence_strength=strength,
                interpretation=(
                    f"Price making higher highs but delta making lower highs — "
                    f"{strength} bearish divergence, buying pressure weakening"
                ),
            )

        return DeltaDivergenceResult(
            divergence_detected=False,
            divergence_type=DeltaDivergenceType.NO_DIVERGENCE,
            interpretation="No divergence detected",
        )

    def reset(self):
        self._price_history.clear()
        self._delta_history.clear()

    def _check_bullish_divergence(self) -> bool:
        if len(self._price_history) < 3 or len(self._delta_history) < 3:
            return False
        price_lower = self._price_history[-1] < self._price_history[0]
        delta_higher = self._delta_history[-1] > self._delta_history[0]
        return price_lower and delta_higher

    def _check_bearish_divergence(self) -> bool:
        if len(self._price_history) < 3 or len(self._delta_history) < 3:
            return False
        price_higher = self._price_history[-1] > self._price_history[0]
        delta_lower = self._delta_history[-1] < self._delta_history[0]
        return price_higher and delta_lower

    def _compute_strength(self) -> str:
        if len(self._price_history) < 3:
            return "weak"
        price_move = abs(self._price_history[-1] - self._price_history[0])
        delta_move = abs(self._delta_history[-1] - self._delta_history[0])
        if price_move == 0:
            return "weak"
        ratio = delta_move / price_move
        if ratio > 3:
            return "strong"
        if ratio > 1.5:
            return "moderate"
        return "weak"
