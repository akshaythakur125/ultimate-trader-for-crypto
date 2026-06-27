from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import (
    ExhaustionState,
    FlowWindow,
)


class ExhaustionResult(BaseModel):
    exhaustion_detected: bool = False
    exhaustion_side: ExhaustionState = ExhaustionState.NO_EXHAUSTION
    exhaustion_score: float = 0.0
    exhaustion_reason: str = ""


class ExhaustionDetector:
    def __init__(
        self,
        volume_fade_threshold: float = 0.5,
        history_length: int = 10,
    ):
        self.volume_fade_threshold = volume_fade_threshold
        self.history_length = history_length
        self._history: list[FlowWindow] = []

    def analyze(self, window: FlowWindow) -> ExhaustionResult:
        self._history.append(window)
        if len(self._history) > self.history_length:
            self._history.pop(0)

        if len(self._history) < 3:
            return ExhaustionResult(exhaustion_reason="Insufficient window history")

        buyer_exhausted = self._check_buyer_exhaustion()
        seller_exhausted = self._check_seller_exhaustion()

        if buyer_exhausted and seller_exhausted:
            return ExhaustionResult(
                exhaustion_detected=True,
                exhaustion_side=ExhaustionState.NO_EXHAUSTION,
                exhaustion_score=50.0,
                exhaustion_reason="Both sides show exhaustion signals — indecision",
            )

        if buyer_exhausted:
            score = self._compute_exhaustion_score("buyer")
            return ExhaustionResult(
                exhaustion_detected=True,
                exhaustion_side=ExhaustionState.BUYER_EXHAUSTION,
                exhaustion_score=score,
                exhaustion_reason=f"Buyer exhaustion detected: declining aggression score={score:.0f}%",
            )

        if seller_exhausted:
            score = self._compute_exhaustion_score("seller")
            return ExhaustionResult(
                exhaustion_detected=True,
                exhaustion_side=ExhaustionState.SELLER_EXHAUSTION,
                exhaustion_score=score,
                exhaustion_reason=f"Seller exhaustion detected: declining aggression score={score:.0f}%",
            )

        return ExhaustionResult(
            exhaustion_detected=False,
            exhaustion_side=ExhaustionState.NO_EXHAUSTION,
            exhaustion_reason="No exhaustion detected",
        )

    def reset(self):
        self._history.clear()

    def _check_buyer_exhaustion(self) -> bool:
        if len(self._history) < 3:
            return False
        recent = self._history[-3:]
        buy_volumes = [w.total_buy_volume for w in recent]
        if buy_volumes[0] == 0:
            return False
        fade = buy_volumes[-1] / buy_volumes[0]
        return fade < self.volume_fade_threshold and buy_volumes[-1] < buy_volumes[-2]

    def _check_seller_exhaustion(self) -> bool:
        if len(self._history) < 3:
            return False
        recent = self._history[-3:]
        sell_volumes = [w.total_sell_volume for w in recent]
        if sell_volumes[0] == 0:
            return False
        fade = sell_volumes[-1] / sell_volumes[0]
        return fade < self.volume_fade_threshold and sell_volumes[-1] < sell_volumes[-2]

    def _compute_exhaustion_score(self, side: str) -> float:
        if len(self._history) < 2:
            return 0.0
        first = self._history[0]
        last = self._history[-1]
        if side == "buyer":
            if first.total_buy_volume == 0:
                return 0.0
            fade_ratio = last.total_buy_volume / first.total_buy_volume
        else:
            if first.total_sell_volume == 0:
                return 0.0
            fade_ratio = last.total_sell_volume / first.total_sell_volume
        score = (1.0 - fade_ratio) * 100
        return round(min(max(score, 0), 100), 2)
