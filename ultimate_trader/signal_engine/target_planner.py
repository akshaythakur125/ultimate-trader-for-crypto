from typing import Optional

from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.trade_plan import TargetPlan


class TargetPlanner:
    def plan_targets(
        self,
        ctx: SignalContext,
        entry_price: float,
        stop_price: float,
        minimum_rr: float = 3.0,
        preferred_rr: float = 5.0,
    ) -> TargetPlan:
        risk = abs(entry_price - stop_price)
        if risk == 0:
            return TargetPlan(
                target_id=f"TP-{ctx.context_id[:8].upper()}",
                take_profit_1=entry_price,
                target_reason="No risk defined, target at entry",
                target_realism_score=0.0,
                expected_reward_r=0.0,
            )

        tp1 = entry_price + (risk * preferred_rr) if ctx.direction_bias.value == "LONG" else entry_price - (risk * preferred_rr)
        tp2 = entry_price + (risk * preferred_rr * 1.5) if ctx.direction_bias.value == "LONG" else entry_price - (risk * preferred_rr * 1.5)
        tp3 = entry_price + (risk * preferred_rr * 2.0) if ctx.direction_bias.value == "LONG" else entry_price - (risk * preferred_rr * 2.0)

        reward_r = abs(tp1 - entry_price) / risk if risk > 0 else 0.0
        realism = self._calculate_realism(ctx, reward_r)

        partial_exit = "Exit 50% at TP1, 30% at TP2, 20% at TP3" if realism >= 50 else "Exit 100% at TP1"

        return TargetPlan(
            target_id=f"TP-{ctx.context_id[:8].upper()}",
            take_profit_1=round(tp1, 8),
            take_profit_2=round(tp2, 8),
            take_profit_3=round(tp3, 8),
            target_reason=f"Targets based on {preferred_rr}:1 R:R minimum",
            target_realism_score=round(realism, 2),
            nearby_obstacles=self._identify_obstacles(ctx, reward_r),
            expected_reward_r=round(reward_r, 4),
            partial_exit_plan=partial_exit,
        )

    def _calculate_realism(self, ctx: SignalContext, reward_r: float) -> float:
        score = 75.0
        if ctx.volatility_score > 60:
            score -= 15.0
        if ctx.uncertainty_score > 50:
            score -= 10.0
        if ctx.manipulation_score > 50:
            score -= 10.0
        if reward_r > 8.0:
            score -= 15.0
        return max(0.0, min(100.0, score))

    def _identify_obstacles(self, ctx: SignalContext, reward_r: float) -> str:
        obstacles = []
        if ctx.manipulation_score > 50:
            obstacles.append("Manipulation zones near target")
        if ctx.liquidity_score < 30:
            obstacles.append("Low liquidity may prevent target filling")
        if reward_r > 8.0:
            obstacles.append("Target may be too ambitious for current volatility")
        return "; ".join(obstacles) if obstacles else "No major obstacles identified"
