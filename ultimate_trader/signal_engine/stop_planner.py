from typing import Optional

from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.trade_plan import StopPlan, StopType


class InvalidStopError(ValueError):
    pass


class StopPlanner:
    MAX_RISK_PERCENT = 2.0
    MIN_STOP_DISTANCE_BPS = 10

    def plan_stop(
        self,
        ctx: SignalContext,
        entry_price: float,
    ) -> StopPlan:
        if entry_price <= 0:
            raise InvalidStopError("Entry price must be positive")

        volatility_distance = entry_price * (ctx.volatility_score / 1000.0)

        if ctx.direction_bias.value == "LONG":
            stop_price = entry_price - volatility_distance
        else:
            stop_price = entry_price + volatility_distance

        distance_pct = abs(entry_price - stop_price) / entry_price * 100

        is_too_obvious = distance_pct < self.MIN_STOP_DISTANCE_BPS / 1000.0
        warning = None

        if is_too_obvious:
            warning = "Stop is too tight/obvious, may be swept"

        if distance_pct > self.MAX_RISK_PERCENT:
            warning = f"Stop distance ({distance_pct:.2f}%) exceeds max risk ({self.MAX_RISK_PERCENT}%)"

        stop_type = self._determine_stop_type(ctx)

        return StopPlan(
            stop_id=f"SP-{ctx.context_id[:8].upper()}",
            stop_loss_price=round(stop_price, 8),
            stop_type=stop_type,
            stop_reason=self._reason_for_stop(stop_type, ctx),
            distance_from_entry_percent=round(distance_pct, 4),
            max_adverse_excursion_allowed_r=round(distance_pct / 100.0 * 5, 2),
            stop_is_too_obvious=is_too_obvious,
            stop_warning=warning,
        )

    def _determine_stop_type(self, ctx: SignalContext) -> StopType:
        if ctx.manipulation_score > 50:
            return StopType.LIQUIDITY_LEVEL_INVALIDATION
        if ctx.volatility_score > 60:
            return StopType.VOLATILITY_BASED
        if ctx.uncertainty_score > 50:
            return StopType.TIME_BASED_INVALIDATION
        return StopType.STRUCTURE_INVALIDATION

    def _reason_for_stop(self, stop_type: StopType, ctx: SignalContext) -> str:
        reasons = {
            StopType.STRUCTURE_INVALIDATION: "Stop at structure level — break invalidates hypothesis",
            StopType.VOLATILITY_BASED: "Stop sized for current volatility conditions",
            StopType.LIQUIDITY_LEVEL_INVALIDATION: "Stop beyond liquidity level to avoid sweep",
            StopType.TIME_BASED_INVALIDATION: "Time-based stop due to high uncertainty",
        }
        return reasons.get(stop_type, "Standard stop loss placement")
