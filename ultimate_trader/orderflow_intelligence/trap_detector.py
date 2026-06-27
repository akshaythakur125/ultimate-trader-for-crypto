from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import (
    AbsorptionState,
    AggressionBias,
    FlowWindow,
    TrapAction,
    TrapRisk,
)


class TrapDetectionResult(BaseModel):
    trap_detected: bool = False
    trap_type: TrapRisk = TrapRisk.UNKNOWN
    trap_score: float = 0.0
    trap_reason: str = ""
    recommended_action: TrapAction = TrapAction.WAIT


class TrapDetector:
    def __init__(
        self,
        aggression_threshold: float = 0.65,
        absorption_threshold: float = 0.6,
        history_length: int = 10,
    ):
        self.aggression_threshold = aggression_threshold
        self.absorption_threshold = absorption_threshold
        self.history_length = history_length
        self._history: list[dict] = []

    def analyze(
        self,
        window: FlowWindow,
        aggression_bias: AggressionBias,
        absorption_type: AbsorptionState,
        delta_divergence: str,
    ) -> TrapDetectionResult:
        self._history.append({
            "window": window,
            "aggression": aggression_bias,
            "absorption": absorption_type,
        })
        if len(self._history) > self.history_length:
            self._history.pop(0)

        long_trap = self._detect_long_trap(window, aggression_bias, absorption_type, delta_divergence)
        short_trap = self._detect_short_trap(window, aggression_bias, absorption_type, delta_divergence)

        if long_trap and short_trap:
            return TrapDetectionResult(
                trap_detected=True,
                trap_type=TrapRisk.LOW_TRAP_RISK,
                trap_score=30.0,
                trap_reason="Conflicting long and short trap signals — mixed",
                recommended_action=TrapAction.COLLECT_MORE_DATA,
            )

        if long_trap:
            score = self._compute_trap_score(window)
            action = TrapAction.BLOCK_TRADE if score > 70 else TrapAction.CAUTION
            return TrapDetectionResult(
                trap_detected=True,
                trap_type=TrapRisk.LONG_TRAP_RISK,
                trap_score=score,
                trap_reason=f"Long trap: buying into absorption or weak breakout (score={score:.0f}/100)",
                recommended_action=action,
            )

        if short_trap:
            score = self._compute_trap_score(window)
            action = TrapAction.BLOCK_TRADE if score > 70 else TrapAction.CAUTION
            return TrapDetectionResult(
                trap_detected=True,
                trap_type=TrapRisk.SHORT_TRAP_RISK,
                trap_score=score,
                trap_reason=f"Short trap: selling into absorption or weak breakdown (score={score:.0f}/100)",
                recommended_action=action,
            )

        return TrapDetectionResult(
            trap_detected=False,
            trap_type=TrapRisk.LOW_TRAP_RISK,
            trap_score=10.0,
            trap_reason="No trap conditions detected",
            recommended_action=TrapAction.WAIT,
        )

    def reset(self):
        self._history.clear()

    def _detect_long_trap(
        self,
        window: FlowWindow,
        aggression: AggressionBias,
        absorption: AbsorptionState,
        divergence: str,
    ) -> bool:
        signals = 0
        if aggression == AggressionBias.BUYER_AGGRESSION and absorption == AbsorptionState.BUYING_ABSORBED:
            signals += 2
        if divergence == "BEARISH_DIVERGENCE":
            signals += 1
        if self._detect_weak_breakout(window):
            signals += 1
        return signals >= 2

    def _detect_short_trap(
        self,
        window: FlowWindow,
        aggression: AggressionBias,
        absorption: AbsorptionState,
        divergence: str,
    ) -> bool:
        signals = 0
        if aggression == AggressionBias.SELLER_AGGRESSION and absorption == AbsorptionState.SELLING_ABSORBED:
            signals += 2
        if divergence == "BULLISH_DIVERGENCE":
            signals += 1
        if self._detect_weak_breakdown(window):
            signals += 1
        return signals >= 2

    def _compute_trap_score(self, window: FlowWindow) -> float:
        base = 40.0
        if window.trade_count > 20:
            base += 15
        if window.large_trade_count > 3:
            base += 15
        if window.buy_sell_delta == 0:
            base += 10
        return round(min(base, 100), 2)

    def _detect_weak_breakout(self, window: FlowWindow) -> bool:
        if window.trade_count < 5:
            return False
        buy_ratio = window.total_buy_volume / (window.total_buy_volume + window.total_sell_volume) if (window.total_buy_volume + window.total_sell_volume) > 0 else 0
        return 0.45 <= buy_ratio <= 0.55 and window.large_trade_count <= 1

    def _detect_weak_breakdown(self, window: FlowWindow) -> bool:
        if window.trade_count < 5:
            return False
        sell_ratio = window.total_sell_volume / (window.total_buy_volume + window.total_sell_volume) if (window.total_buy_volume + window.total_sell_volume) > 0 else 0
        return 0.45 <= sell_ratio <= 0.55 and window.large_trade_count <= 1
