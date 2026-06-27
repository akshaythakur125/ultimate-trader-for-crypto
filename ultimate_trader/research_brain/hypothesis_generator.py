from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DirectionBias(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"


class HypothesisStatus(str, Enum):
    GENERATED = "GENERATED"
    COMPETING = "COMPETING"
    FALSIFIED = "FALSIFIED"
    WEAK = "WEAK"
    SHORTLISTED = "SHORTLISTED"
    REJECTED = "REJECTED"
    READY_FOR_BACKTEST = "READY_FOR_BACKTEST"


class ResearchHypothesis(BaseModel):
    research_id: str
    name: str
    description: str = ""
    direction_bias: DirectionBias
    market_explanation: str = ""
    expected_market_behavior: str = ""
    required_evidence: list[str] = Field(default_factory=list)
    invalidating_evidence: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    expected_rr: float = 0.0
    expected_holding_time_hours: float = 0.0
    expected_failure_modes: list[str] = Field(default_factory=list)
    regime_dependency: str = ""
    liquidity_dependency: str = ""
    orderflow_dependency: str = ""
    memory_support_summary: Optional[str] = None
    bayesian_prior: Optional[float] = None
    bayesian_posterior: Optional[float] = None
    expected_value_r: Optional[float] = None
    status: HypothesisStatus = HypothesisStatus.GENERATED
    rejection_reason: Optional[str] = None


class HypothesisGenerationContext(BaseModel):
    symbol: str
    timeframe: str
    market_observations: list[str] = Field(default_factory=list)
    cognitive_context: Optional[str] = None
    metacognitive_context: Optional[str] = None
    memory_report: Optional[str] = None
    belief_state: Optional[str] = None
    market_principles: Optional[str] = None
    constraints: list[str] = Field(default_factory=list)
    generation_goal: str = "explore"


class HypothesisGenerator:
    FAMILIES = [
        "BREAKOUT_CONTINUATION",
        "LIQUIDITY_SWEEP_REVERSAL",
        "LIQUIDITY_SWEEP_CONTINUATION",
        "FALSE_BREAKOUT",
        "SHORT_SQUEEZE",
        "LONG_SQUEEZE",
        "RANGE_CONTINUATION",
        "MEAN_REVERSION",
        "TREND_EXHAUSTION",
        "VOLATILITY_EXPANSION",
        "CHOP_NO_TRADE",
        "NO_EDGE",
    ]

    def generate(self, ctx: HypothesisGenerationContext) -> list[ResearchHypothesis]:
        return [
            self._build_breakout_continuation(ctx),
            self._build_liquidity_sweep_reversal(ctx),
            self._build_liquidity_sweep_continuation(ctx),
            self._build_false_breakout(ctx),
            self._build_short_squeeze(ctx),
            self._build_long_squeeze(ctx),
            self._build_range_continuation(ctx),
            self._build_mean_reversion(ctx),
            self._build_trend_exhaustion(ctx),
            self._build_volatility_expansion(ctx),
            self._build_chop_no_trade(ctx),
            self._build_no_edge(ctx),
        ]

    def generate_by_family(
        self,
        ctx: HypothesisGenerationContext,
        family: str,
    ) -> ResearchHypothesis:
        builder = {
            "BREAKOUT_CONTINUATION": self._build_breakout_continuation,
            "LIQUIDITY_SWEEP_REVERSAL": self._build_liquidity_sweep_reversal,
            "LIQUIDITY_SWEEP_CONTINUATION": self._build_liquidity_sweep_continuation,
            "FALSE_BREAKOUT": self._build_false_breakout,
            "SHORT_SQUEEZE": self._build_short_squeeze,
            "LONG_SQUEEZE": self._build_long_squeeze,
            "RANGE_CONTINUATION": self._build_range_continuation,
            "MEAN_REVERSION": self._build_mean_reversion,
            "TREND_EXHAUSTION": self._build_trend_exhaustion,
            "VOLATILITY_EXPANSION": self._build_volatility_expansion,
            "CHOP_NO_TRADE": self._build_chop_no_trade,
            "NO_EDGE": self._build_no_edge,
        }
        builder_fn = builder.get(family, self._build_no_edge)
        return builder_fn(ctx)

    def _make_id(self) -> str:
        import uuid
        return f"RH-{uuid.uuid4().hex[:8].upper()}"

    def _build_breakout_continuation(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Breakout Continuation",
            description="Price breaks a key level and continues in the breakout direction",
            direction_bias=DirectionBias.LONG,
            market_explanation="Price broke through a significant support/resistance level "
                              "with momentum, suggesting continuation.",
            expected_market_behavior="Price continues in breakout direction within 1-3 bars",
            required_evidence=["Breakout of established range", "Volume confirmation",
                               "No immediate reversal below breakout level"],
            invalidating_evidence=["Price returns below breakout level",
                                   "Reversal candlestick pattern at breakout"],
            expected_failure_modes=["False breakout", "Liquidity grab", "Trend exhaustion"],
            regime_dependency="trending",
            liquidity_dependency="normal",
            orderflow_dependency="aggressive",
            expected_rr=3.0,
            expected_holding_time_hours=6.0,
        )

    def _build_liquidity_sweep_reversal(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Liquidity Sweep Reversal",
            description="Price sweeps resting liquidity then reverses sharply",
            direction_bias=DirectionBias.SHORT,
            market_explanation="Market swept above/below obvious liquidity zones, "
                              "trapped late traders, and is now reversing.",
            expected_market_behavior="Sharp reversal after liquidity grab, "
                                     "returning through sweep level",
            required_evidence=["Sweep of recent high/low", "Rejection wick",
                               "Follow-through in opposite direction"],
            invalidating_evidence=["Price continues past sweep level",
                                   "No reversal within 2 bars"],
            expected_failure_modes=["Continued momentum past liquidity", "Second sweep"],
            regime_dependency="ranging",
            liquidity_dependency="normal",
            orderflow_dependency="aggressive",
            expected_rr=3.5,
            expected_holding_time_hours=4.0,
        )

    def _build_liquidity_sweep_continuation(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Liquidity Sweep Continuation",
            description="Price sweeps liquidity and continues in original trend",
            direction_bias=DirectionBias.LONG,
            market_explanation="Liquidity sweep acted as a re-accumulation zone, "
                              "then trend resumed.",
            required_evidence=["Sweep of liquidity zone", "Quick recovery",
                               "Trend remains intact"],
            invalidating_evidence=["Failed to recover sweep level", "Reversal follows"],
            expected_failure_modes=["Real reversal", "Double sweep"],
            regime_dependency="trending",
            liquidity_dependency="normal",
            orderflow_dependency="aggressive",
            expected_rr=4.0,
            expected_holding_time_hours=8.0,
        )

    def _build_false_breakout(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="False Breakout",
            description="Brief move beyond key level that immediately fails",
            direction_bias=DirectionBias.NEUTRAL,
            market_explanation="Price broke a level briefly but lacked follow-through, "
                              "trapping breakout traders.",
            required_evidence=["Brief break of level", "Low volume on breakout",
                               "Immediate reversal"],
            invalidating_evidence=["Sustained price beyond level",
                                   "Increasing volume on breakout"],
            expected_failure_modes=["Real breakout", "Range expansion"],
            regime_dependency="ranging",
            liquidity_dependency="normal",
            orderflow_dependency="neutral",
            expected_rr=2.0,
            expected_holding_time_hours=2.0,
        )

    def _build_short_squeeze(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Short Squeeze",
            description="Rapid price increase forcing short covering",
            direction_bias=DirectionBias.LONG,
            market_explanation="Elevated short interest combined with upward pressure "
                              "is forcing shorts to cover, accelerating price up.",
            required_evidence=["Elevated short interest", "Rapid upward moves",
                               "Increasing volume"],
            invalidating_evidence=["Short interest declining", "No follow-through"],
            expected_failure_modes=["Squeeze exhausted", "Mean reversion after squeeze"],
            regime_dependency="volatile",
            liquidity_dependency="thin",
            orderflow_dependency="aggressive_buying",
            expected_rr=3.0,
            expected_holding_time_hours=2.0,
        )

    def _build_long_squeeze(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Long Squeeze",
            description="Rapid price decrease forcing long liquidation",
            direction_bias=DirectionBias.SHORT,
            market_explanation="Overcrowded long positions are being liquidated, "
                              "accelerating price down.",
            required_evidence=["Overextended longs", "Rapid downward moves",
                               "Cascade selling"],
            invalidating_evidence=["Buying pressure returns", "No cascade"],
            expected_failure_modes=["Squeeze exhausted", "Dead cat bounce"],
            regime_dependency="volatile",
            liquidity_dependency="thin",
            orderflow_dependency="aggressive_selling",
            expected_rr=3.0,
            expected_holding_time_hours=2.0,
        )

    def _build_range_continuation(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Range Continuation",
            description="Price remains within established range boundaries",
            direction_bias=DirectionBias.NEUTRAL,
            market_explanation="Price is respecting range boundaries with no "
                              "breakout momentum.",
            required_evidence=["Clear range high/low", "Respected boundaries",
                               "No breakout catalyst"],
            invalidating_evidence=["Breakout from range", "Volatility expansion"],
            expected_failure_modes=["False range break", "Range contraction into breakout"],
            regime_dependency="ranging",
            liquidity_dependency="normal",
            orderflow_dependency="neutral",
            expected_rr=1.0,
            expected_holding_time_hours=4.0,
        )

    def _build_mean_reversion(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Mean Reversion",
            description="Price returns toward its mean after extreme move",
            direction_bias=DirectionBias.NEUTRAL,
            market_explanation="Price deviated significantly from its moving average "
                              "and is likely to revert toward it.",
            required_evidence=["Extreme deviation from MA", "Overbought/oversold",
                               "Momentum slowing"],
            invalidating_evidence=["Continued deviation", "New trend established"],
            expected_failure_modes=["Trend continuation", "New equilibrium"],
            regime_dependency="ranging",
            liquidity_dependency="normal",
            orderflow_dependency="neutral",
            expected_rr=2.0,
            expected_holding_time_hours=6.0,
        )

    def _build_trend_exhaustion(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Trend Exhaustion",
            description="Current trend is losing momentum and may reverse or pause",
            direction_bias=DirectionBias.NEUTRAL,
            market_explanation="Trend shows signs of weakening: momentum divergence, "
                              "reduced volume, and slowing price progress.",
            required_evidence=["Momentum divergence", "Declining volume on trend moves",
                               "Slowing price progression"],
            invalidating_evidence=["Momentum re-acceleration", "Fresh catalyst"],
            expected_failure_modes=["Trend resumption", "Sideways consolidation"],
            regime_dependency="trending",
            liquidity_dependency="normal",
            orderflow_dependency="declining",
            expected_rr=2.5,
            expected_holding_time_hours=8.0,
        )

    def _build_volatility_expansion(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Volatility Expansion",
            description="Compressed volatility is about to expand significantly",
            direction_bias=DirectionBias.NEUTRAL,
            market_explanation="Volatility has compressed to extreme levels, "
                              "historically preceding large directional moves.",
            required_evidence=["Low ATR", "Tight range", "Compression pattern"],
            invalidating_evidence=["Continued compression", "False expansion"],
            expected_failure_modes=["Fakeout", "Continued compression"],
            regime_dependency="volatile",
            liquidity_dependency="normal",
            orderflow_dependency="neutral",
            expected_rr=3.0,
            expected_holding_time_hours=12.0,
        )

    def _build_chop_no_trade(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="Chop / No Trade",
            description="Market is too choppy for any reliable directional hypothesis",
            direction_bias=DirectionBias.NO_TRADE,
            market_explanation="Price action is erratic with no clear structure. "
                              "Multiple timeframes show conflicting signals.",
            required_evidence=["Erratic price action", "No clear structure",
                               "Conflicting timeframe signals"],
            invalidating_evidence=["Clear pattern emerges", "Volatility contraction stabilizes"],
            expected_failure_modes=["Fakeout losses", "Whiplash"],
            regime_dependency="any",
            liquidity_dependency="any",
            orderflow_dependency="any",
            expected_rr=0.0,
            expected_holding_time_hours=0.0,
        )

    def _build_no_edge(
        self, ctx: HypothesisGenerationContext
    ) -> ResearchHypothesis:
        return ResearchHypothesis(
            research_id=self._make_id(),
            name="No Edge",
            description="No clear statistical edge can be identified",
            direction_bias=DirectionBias.NO_TRADE,
            market_explanation="After analyzing all available information, "
                              "no hypothesis has sufficient evidence or edge.",
            required_evidence=["Insufficient evidence for any hypothesis",
                               "All competing hypotheses have critical gaps"],
            invalidating_evidence=["New evidence emerges that favors one hypothesis"],
            expected_failure_modes=["Missing a real opportunity"],
            regime_dependency="any",
            liquidity_dependency="any",
            orderflow_dependency="any",
            expected_rr=0.0,
            expected_holding_time_hours=0.0,
        )
