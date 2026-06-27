from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import FlowWindow


class FlowMomentumResult(BaseModel):
    flow_momentum_score: float = 0.0
    acceleration: str = ""
    persistence: str = ""
    reversal_risk: str = ""
    summary: str = ""


class FlowMomentumAnalyzer:
    def __init__(self, history_length: int = 10):
        self.history_length = history_length
        self._history: list[FlowWindow] = []

    def analyze(self, window: FlowWindow) -> FlowMomentumResult:
        self._history.append(window)
        if len(self._history) > self.history_length:
            self._history.pop(0)

        if len(self._history) < 3:
            return FlowMomentumResult(
                flow_momentum_score=50.0,
                summary="Building momentum history",
            )

        delta_values = [w.buy_sell_delta for w in self._history[-5:]]
        latest_delta = abs(window.buy_sell_delta) if window.buy_sell_delta != 0 else 0

        short_term_dir = 1 if delta_values[-1] > delta_values[-2] else -1 if len(delta_values) >= 2 else 0
        medium_term_dir = 1 if delta_values[-1] > delta_values[0] else -1

        acceleration = self._detect_acceleration(delta_values)
        persistence = self._detect_persistence(delta_values)
        reversal_risk = self._detect_reversal_risk(delta_values)
        momentum_score = self._compute_momentum_score(delta_values, acceleration, persistence)

        return FlowMomentumResult(
            flow_momentum_score=round(momentum_score, 2),
            acceleration=acceleration,
            persistence=persistence,
            reversal_risk=reversal_risk,
            summary=(
                f"momentum={momentum_score:.0f}/100, "
                f"acceleration={acceleration}, "
                f"persistence={persistence}, "
                f"reversal_risk={reversal_risk}"
            ),
        )

    def reset(self):
        self._history.clear()

    def _detect_acceleration(self, deltas: list[float]) -> str:
        if len(deltas) < 3:
            return "stable"
        recent = deltas[-3:]
        if all(abs(d) >= abs(recent[0]) * 1.2 for d in recent[1:] if recent[0] != 0):
            return "accelerating"
        if all(abs(d) <= abs(recent[0]) * 0.8 for d in recent[1:] if recent[0] != 0):
            return "decelerating"
        return "stable"

    def _detect_persistence(self, deltas: list[float]) -> str:
        if len(deltas) < 3:
            return "unknown"
        positive_count = sum(1 for d in deltas[-3:] if d > 0)
        negative_count = sum(1 for d in deltas[-3:] if d < 0)
        if positive_count >= 3:
            return "strong_buyer_persistence"
        if negative_count >= 3:
            return "strong_seller_persistence"
        if positive_count >= 2:
            return "moderate_buyer_persistence"
        if negative_count >= 2:
            return "moderate_seller_persistence"
        return "mixed"

    def _detect_reversal_risk(self, deltas: list[float]) -> str:
        if len(deltas) < 4:
            return "low"
        if all(d > 0 for d in deltas[-3:]) and deltas[-1] < deltas[-2]:
            return "elevated"
        if all(d < 0 for d in deltas[-3:]) and deltas[-1] > deltas[-2]:
            return "elevated"
        if abs(deltas[-1]) < abs(deltas[-2]) * 0.5 and abs(deltas[-2]) > abs(deltas[-3]):
            return "moderate"
        return "low"

    def _compute_momentum_score(
        self, deltas: list[float], acceleration: str, persistence: str
    ) -> float:
        base = 50.0
        if acceleration == "accelerating":
            base += 15
        elif acceleration == "decelerating":
            base -= 10
        if "strong" in persistence:
            base += 15
        elif "moderate" in persistence:
            base += 5
        elif persistence == "mixed":
            base -= 5
        return min(max(base, 0), 100)
