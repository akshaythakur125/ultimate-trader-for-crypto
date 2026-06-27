from typing import Optional

from ultimate_trader.signal_engine.signal_context import (
    DirectionBias,
    SignalContext,
)
from ultimate_trader.signal_engine.trade_plan import EntryType, EntryZone


class NoSafeEntryError(ValueError):
    pass


class EntryPlanner:
    def plan_entry(self, ctx: SignalContext) -> EntryZone:
        if not ctx.validation_passed:
            return self._no_safe_entry(ctx, "Validation did not pass")

        if ctx.uncertainty_score > 70:
            return self._no_safe_entry(ctx, "Uncertainty too high")

        if ctx.risk_score > 75:
            return self._no_safe_entry(ctx, "Risk score too high")

        if ctx.expected_value_r <= 0:
            return self._no_safe_entry(ctx, "Non-positive expected value")

        if ctx.no_trade_probability and ctx.no_trade_probability > 0.5:
            return self._no_safe_entry(ctx, "No-trade probability dominant")

        spread_buffer = ctx.current_price * (ctx.volatility_score / 10000.0)
        entry_min = ctx.current_price - spread_buffer
        entry_max = ctx.current_price + spread_buffer
        preferred = ctx.current_price

        entry_type = self._determine_entry_type(ctx)

        return EntryZone(
            entry_zone_id=f"EZ-{ctx.context_id[:8].upper()}",
            symbol=ctx.symbol,
            direction=ctx.direction_bias,
            entry_min=round(entry_min, 8),
            entry_max=round(entry_max, 8),
            preferred_entry=round(preferred, 8),
            entry_type=entry_type,
            entry_reason=self._reason_for_entry_type(entry_type, ctx),
        )

    def _no_safe_entry(self, ctx: SignalContext, reason: str) -> EntryZone:
        return EntryZone(
            entry_zone_id=f"EZ-{ctx.context_id[:8].upper()}",
            symbol=ctx.symbol,
            direction=ctx.direction_bias,
            entry_type=EntryType.NO_SAFE_ENTRY,
            entry_reason=reason,
        )

    def _determine_entry_type(self, ctx: SignalContext) -> EntryType:
        if ctx.manipulation_score > 60:
            return EntryType.RETEST_ENTRY
        if ctx.orderflow_score > 60:
            return EntryType.BREAKOUT_CONFIRMATION
        if ctx.volatility_score < 30:
            return EntryType.PULLBACK_ENTRY
        if ctx.liquidity_score > 50:
            return EntryType.RECLAIM_ENTRY
        return EntryType.LIMIT_ZONE

    def _reason_for_entry_type(self, entry_type: EntryType, ctx: SignalContext) -> str:
        reasons = {
            EntryType.LIMIT_ZONE: "Limit entry within volatility-adjusted zone around current price",
            EntryType.BREAKOUT_CONFIRMATION: "Entry on breakout confirmation with orderflow support",
            EntryType.PULLBACK_ENTRY: "Entry on pullback in low-volatility conditions",
            EntryType.RECLAIM_ENTRY: "Entry on reclaim of key level with liquidity support",
            EntryType.RETEST_ENTRY: "Entry on retest after manipulation sweep",
            EntryType.NO_SAFE_ENTRY: ctx.notes or "No safe entry available",
        }
        return reasons.get(entry_type, "Standard entry zone")
