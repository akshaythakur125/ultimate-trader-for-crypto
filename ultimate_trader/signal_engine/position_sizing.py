from typing import Optional

from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.trade_plan import PositionSizingSuggestion


class PositionSizer:
    BASE_RISK_PERCENT = 1.0
    MAX_RISK_PERCENT = 2.0

    def size(
        self,
        ctx: SignalContext,
        account_equity: Optional[float] = None,
    ) -> PositionSizingSuggestion:
        risk_pct = self.BASE_RISK_PERCENT

        if ctx.uncertainty_score > 50:
            risk_pct *= 0.5
        if ctx.contradiction_score and ctx.contradiction_score > 50:
            risk_pct *= 0.5
        if ctx.memory_support_score is not None and ctx.memory_support_score < 30:
            risk_pct *= 0.5
        if ctx.risk_score > 60:
            risk_pct *= 0.7

        risk_pct = max(0.1, min(self.MAX_RISK_PERCENT, risk_pct))

        sizing_reason = self._build_reason(ctx, risk_pct)
        risk_warning = self._build_warning(ctx)

        result = PositionSizingSuggestion(
            sizing_id=f"PS-{ctx.context_id[:8].upper()}",
            account_equity=account_equity,
            max_risk_percent=self.MAX_RISK_PERCENT,
            suggested_risk_percent=round(risk_pct, 4),
            sizing_reason=sizing_reason,
            risk_warning=risk_warning,
        )

        if account_equity is not None and account_equity > 0:
            position_value = account_equity * (risk_pct / 100.0)
            result.position_size_units = round(position_value, 2)

        return result

    def _build_reason(self, ctx: SignalContext, risk_pct: float) -> str:
        parts = [f"Base risk: {self.BASE_RISK_PERCENT}%"]
        if ctx.uncertainty_score > 50:
            parts.append(f"reduced for uncertainty ({ctx.uncertainty_score})")
        if ctx.contradiction_score and ctx.contradiction_score > 50:
            parts.append(f"reduced for contradiction ({ctx.contradiction_score})")
        if ctx.memory_support_score is not None and ctx.memory_support_score < 30:
            parts.append(f"reduced for weak memory support ({ctx.memory_support_score})")
        parts.append(f"final: {risk_pct:.2f}%")
        return "; ".join(parts)

    def _build_warning(self, ctx: SignalContext) -> Optional[str]:
        if ctx.uncertainty_score > 70:
            return "Very high uncertainty — consider waiting or reducing further"
        if ctx.memory_support_score is not None and ctx.memory_support_score < 20:
            return "Very weak memory support — high risk of unknown outcomes"
        return None
