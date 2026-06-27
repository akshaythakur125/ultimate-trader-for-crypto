from typing import Optional

from ultimate_trader.signal_engine.signal_context import SignalContext
from ultimate_trader.signal_engine.trade_plan import (
    CancellationRule,
    ConditionType,
    ExecutionCondition,
)


class ExecutionConditionBuilder:
    def build_conditions(self, ctx: SignalContext) -> list[ExecutionCondition]:
        return [
            ExecutionCondition(
                condition_id="EC-VALIDATION",
                description="Validation passed",
                condition_type=ConditionType.REQUIRED,
                is_satisfied=ctx.validation_passed,
                failure_reason=None if ctx.validation_passed else "Validation not passed",
            ),
            ExecutionCondition(
                condition_id="EC-NO-TRADE",
                description="No-trade probability not dominant",
                condition_type=ConditionType.REQUIRED,
                is_satisfied=ctx.no_trade_probability is None or ctx.no_trade_probability <= 0.5,
                failure_reason="No-trade probability dominant" if ctx.no_trade_probability and ctx.no_trade_probability > 0.5 else None,
            ),
            ExecutionCondition(
                condition_id="EC-EV",
                description="Positive expected value",
                condition_type=ConditionType.REQUIRED,
                is_satisfied=ctx.expected_value_r > 0,
                failure_reason=f"Non-positive EV ({ctx.expected_value_r})" if ctx.expected_value_r <= 0 else None,
            ),
            ExecutionCondition(
                condition_id="EC-RISK",
                description="Daily risk limits not breached",
                condition_type=ConditionType.REQUIRED,
                is_satisfied=ctx.risk_score < 80,
                failure_reason=f"Risk score too high ({ctx.risk_score})" if ctx.risk_score >= 80 else None,
            ),
            ExecutionCondition(
                condition_id="EC-UNCERTAINTY",
                description="Uncertainty within acceptable range",
                condition_type=ConditionType.WARNING,
                is_satisfied=ctx.uncertainty_score < 70,
                failure_reason=f"High uncertainty ({ctx.uncertainty_score})" if ctx.uncertainty_score >= 70 else None,
            ),
        ]


class CancellationRuleBuilder:
    def build_rules(self) -> list[CancellationRule]:
        return [
            CancellationRule(
                rule_id="CR-PRICE-MOVE",
                description="Cancel if price moves away before entry",
                cancel_if_triggered=True,
                reason="Price moved beyond acceptable entry zone",
            ),
            CancellationRule(
                rule_id="CR-INVALIDATION",
                description="Cancel if invalidation level breaks before entry",
                cancel_if_triggered=True,
                reason="Invalidation level breached before entry filled",
            ),
            CancellationRule(
                rule_id="CR-SPREAD",
                description="Cancel if spread becomes too wide",
                cancel_if_triggered=True,
                reason="Spread exceeds maximum acceptable threshold",
            ),
            CancellationRule(
                rule_id="CR-VOLATILITY",
                description="Cancel if volatility spike invalidates stop",
                cancel_if_triggered=True,
                reason="Volatility spike makes stop placement unsafe",
            ),
            CancellationRule(
                rule_id="CR-NO-TRADE",
                description="Cancel if no-trade probability becomes dominant",
                cancel_if_triggered=True,
                reason="No-trade probability exceeded threshold",
            ),
            CancellationRule(
                rule_id="CR-CONTRADICTION",
                description="Cancel if contradiction score rises",
                cancel_if_triggered=True,
                reason="Contradiction score increased, hypothesis weakened",
            ),
            CancellationRule(
                rule_id="CR-VALIDATION",
                description="Cancel if validation status becomes invalid",
                cancel_if_triggered=True,
                reason="Validation re-check failed",
            ),
            CancellationRule(
                rule_id="CR-EXPIRY",
                description="Cancel if trade expires",
                cancel_if_triggered=True,
                reason="Trade plan expired",
            ),
        ]
