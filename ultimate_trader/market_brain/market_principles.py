from enum import Enum

from pydantic import BaseModel, Field


class CategoryEnum(str, Enum):
    AUCTION_MARKET = "AUCTION_MARKET"
    LIQUIDITY = "LIQUIDITY"
    ORDER_FLOW = "ORDER_FLOW"
    VOLATILITY = "VOLATILITY"
    REGIME = "REGIME"
    MANIPULATION = "MANIPULATION"
    BEHAVIORAL = "BEHAVIORAL"
    RISK = "RISK"
    PROBABILITY = "PROBABILITY"


class MarketPrinciple(BaseModel):
    principle_id: str
    name: str
    category: CategoryEnum
    description: str
    why_it_matters: str
    intraday_relevance: str
    failure_conditions: str
    related_observations: list[str] = Field(default_factory=list)


AUCTION_PRINCIPLES = [
    MarketPrinciple(
        principle_id="AMT-001",
        name="Price moves to facilitate trade",
        category=CategoryEnum.AUCTION_MARKET,
        description="Price moves to find the level where the most trade can occur. "
        "Directional movement happens when imbalance exists between buyers and sellers.",
        why_it_matters="Understanding that price is not random — it is searching for liquidity. "
        "This helps distinguish between noise and genuine price discovery.",
        intraday_relevance="Intraday moves often reflect temporary imbalances. "
        "Observing where price finds acceptance or rejection reveals the market's current equilibrium.",
        failure_conditions="In low-volume or manipulated environments, price may not reflect true "
        "acceptance or rejection.",
        related_observations=["high_volume_nodes", "low_volume_nodes", "price_rejection"],
    ),
    MarketPrinciple(
        principle_id="AMT-002",
        name="Markets seek liquidity",
        category=CategoryEnum.AUCTION_MARKET,
        description="Price is naturally drawn toward areas where resting orders are clustered. "
        "These areas act as magnets until liquidity is consumed.",
        why_it_matters="Predicting where price may go next is often about identifying where "
        "the most liquidity sits.",
        intraday_relevance="Intraday levels such as previous day high/low, round numbers, "
        "and obvious swing points are natural liquidity magnets.",
        failure_conditions="When liquidity is intentionally placed to trap rather than execute, "
        "price may reverse before reaching these levels.",
        related_observations=["liquidity_sweep", "stop_run", "high_volume_node"],
    ),
    MarketPrinciple(
        principle_id="AMT-003",
        name="Imbalance causes directional movement",
        category=CategoryEnum.AUCTION_MARKET,
        description="When aggressive buyers significantly outnumber sellers, price must rise "
        "to attract more sellers. Conversely for aggressive selling.",
        why_it_matters="Identifying imbalance early provides an edge in anticipating directional "
        "moves before they are obvious.",
        intraday_relevance="Order flow and volume profile reveal real-time imbalance. "
        "Delta divergence on low timeframe often precedes larger moves.",
        failure_conditions="Algorithms and spoofing can create false imbalance signals. "
        "Imbalance must be confirmed by actual price movement.",
        related_observations=["delta_divergence", "volume_spike", "orderbook_imbalance"],
    ),
    MarketPrinciple(
        principle_id="AMT-004",
        name="Acceptance versus rejection matters",
        category=CategoryEnum.AUCTION_MARKET,
        description="When price moves to a level and spends time there with participation, "
        "it indicates acceptance. Quick rejection shows weakness of that level.",
        why_it_matters="A level that is rejected is more likely to act as resistance or support. "
        "A level that is accepted may become equilibrium.",
        intraday_relevance="Watch for price to visit a level and either absorb (accept) or "
        "quickly reverse (reject). Rejection at obvious levels is tradeable.",
        failure_conditions="Acceptance can turn into rejection over time as order flow shifts, "
        "so levels need continuous reassessment.",
        related_observations=["price_rejection", "absorption", "high_volume_node"],
    ),
    MarketPrinciple(
        principle_id="AMT-005",
        name="Value migration matters",
        category=CategoryEnum.AUCTION_MARKET,
        description="The price range where most volume occurred (value area) shifts over time. "
        "Migration of value indicates changing market consensus.",
        why_it_matters="Value area provides context for where the market considers price 'fair'. "
        "Deviation from value often returns to value.",
        intraday_relevance="Intraday value area shifts signal changing sentiment. "
        "Price extended above/below value may revert.",
        failure_conditions="Strong trending markets can sustain deviation from value for "
        "extended periods.",
        related_observations=["value_area_high", "value_area_low", "point_of_control"],
    ),
    MarketPrinciple(
        principle_id="AMT-006",
        name="Price discovery requires participation",
        category=CategoryEnum.AUCTION_MARKET,
        description="Meaningful price discovery only occurs when volume confirms movement. "
        "Low-volume breakouts are suspect.",
        why_it_matters="Without participation, price moves are unreliable and prone to reversal.",
        intraday_relevance="Monitor volume relative to average during breakouts. "
        "A breakout on low volume has higher failure probability.",
        failure_conditions="In highly manipulated markets, algorithms can move price without "
        "genuine participation.",
        related_observations=["low_volume_breakout", "volume_divergence", "fakeout"],
    ),
]

LIQUIDITY_PRINCIPLES = [
    MarketPrinciple(
        principle_id="LIQ-001",
        name="Obvious highs/lows attract stops",
        category=CategoryEnum.LIQUIDITY,
        description="Retail traders place stops beyond obvious swing highs and lows. "
        "These clustered stops are known targets for smart money.",
        why_it_matters="Identifying obvious liquidity clusters helps anticipate where price "
        "may be drawn and whether it will reverse or continue after sweeping them.",
        intraday_relevance="Previous day high/low, weekly high/low, and multi-session swing "
        "points are the most obvious intraday stop clusters.",
        failure_conditions="Trending markets may sweep stops and continue without reversal. "
        "Stop sweeps alone are not reversal signals.",
        related_observations=["liquidity_sweep", "stop_hunt", "break_of_structure"],
    ),
    MarketPrinciple(
        principle_id="LIQ-002",
        name="Liquidity sweeps can precede reversals",
        category=CategoryEnum.LIQUIDITY,
        description="Price often sweeps beyond obvious levels to trigger stops, then reverses "
        "sharply. This is a classic liquidity grab pattern.",
        why_it_matters="Recognizing a sweep versus a genuine breakout is critical. "
        "Sweeps followed by reclaim indicate trapped traders.",
        intraday_relevance="Watch for impulsive wicks beyond key levels with immediate reclaim. "
        "This is a high-probability reversal setup.",
        failure_conditions="Not all sweeps reverse. In strong trends, sweeps can be stop runs "
        "that accelerate the move.",
        related_observations=["wick_reclaim", "stop_hunt", "fakeout"],
    ),
    MarketPrinciple(
        principle_id="LIQ-003",
        name="Thin liquidity increases fakeout risk",
        category=CategoryEnum.LIQUIDITY,
        description="When market depth is thin, smaller orders can move price disproportionately. "
        "This creates fake breakouts that reverse quickly.",
        why_it_matters="Trading breakouts during thin liquidity times (lunch hours, "
        "low-volume sessions) has higher false signal risk.",
        intraday_relevance="The first hour after open and the last hours before close "
        "typically have highest liquidity. Mid-session lulls see more false moves.",
        failure_conditions="Algorithmic trading can simulate liquidity. "
        "Apparent thin liquidity may be manipulated.",
        related_observations=["low_volume_breakout", "wide_spread", "orderbook_gap"],
    ),
    MarketPrinciple(
        principle_id="LIQ-004",
        name="Clustered stops can accelerate moves",
        category=CategoryEnum.LIQUIDITY,
        description="When multiple stop-loss orders cluster at the same level, triggering them "
        "creates cascading price movement.",
        why_it_matters="Stop cascades create rapid, self-reinforcing moves. "
        "Knowing where stops cluster helps anticipate acceleration points.",
        intraday_relevance="Round numbers, previous day VAH/VAL, and recent swing points "
        "are common stop cluster locations.",
        failure_conditions="Stop cascades can reverse as quickly as they start once "
        "liquidity is exhausted.",
        related_observations=["stop_run", "cascade", "volume_impulse"],
    ),
    MarketPrinciple(
        principle_id="LIQ-005",
        name="Liquidity is both target and fuel",
        category=CategoryEnum.LIQUIDITY,
        description="The same liquidity that attracts price also provides the fuel for "
        "directional movement. Once consumed, the move may stall.",
        why_it_matters="A move that has consumed all available liquidity has no fuel to continue. "
        "This is where reversals or consolidation occur.",
        intraday_relevance="After a strong impulse move, watch for volume decline — "
        "it signals liquidity exhaustion.",
        failure_conditions="New liquidity can enter at higher prices, extending the move. "
        "Exhaustion is not always permanent.",
        related_observations=["volume_decline", "absorption", "consolidation"],
    ),
    MarketPrinciple(
        principle_id="LIQ-006",
        name="Stop runs exhaust the immediate fuel",
        category=CategoryEnum.LIQUIDITY,
        description="A stop-run that sweeps through clustered stops often exhausts the "
        "immediate directional fuel, leading to reversal or pause.",
        why_it_matters="Identifying exhaustion after a stop run helps avoid chasing "
        "moves that are likely to reverse.",
        intraday_relevance="Look for high-volume impulses that quickly fade. "
        "These often indicate liquidity grab, not genuine breakout.",
        failure_conditions="Strong trends can absorb stop-run exhaust and continue. "
        "Not every stop-run leads to reversal.",
        related_observations=["liquidity_sweep", "volume_spike_reversal", "absorption"],
    ),
]

ORDERFLOW_PRINCIPLES = [
    MarketPrinciple(
        principle_id="OF-001",
        name="Price movement without participation is weak",
        category=CategoryEnum.ORDER_FLOW,
        description="A price move on declining or below-average volume lacks conviction "
        "and is prone to failure.",
        why_it_matters="Volume confirms or rejects price. "
        "Low-volume breakouts have a high failure rate.",
        intraday_relevance="Compare current volume to the average for that time of day. "
        "Breakouts during declining volume should be treated with suspicion.",
        failure_conditions="In highly algorithmic markets, low volume can still produce "
        "directional moves that persist.",
        related_observations=["low_volume_breakout", "volume_divergence", "fakeout"],
    ),
    MarketPrinciple(
        principle_id="OF-002",
        name="Volume confirms or rejects movement",
        category=CategoryEnum.ORDER_FLOW,
        description="Volume is the primary confirmation tool. Rising volume in the direction "
        "of the move confirms participation. Diverging volume warns of reversal.",
        why_it_matters="Volume tells you whether the market agrees with the price move. "
        "Without agreement, the move is suspect.",
        intraday_relevance="Use cumulative delta and volume profile to assess whether "
        "participation supports the price direction.",
        failure_conditions="Volume data from exchanges can include wash trading. "
        "Cross-exchange volume aggregation helps but is not perfect.",
        related_observations=["cumulative_delta", "volume_profile", "price_volume_divergence"],
    ),
    MarketPrinciple(
        principle_id="OF-003",
        name="Aggressive buying into resistance may be absorption",
        category=CategoryEnum.ORDER_FLOW,
        description="When price approaches resistance with aggressive buying but fails to break, "
        "it may be smart money absorbing sell orders to distribute position.",
        why_it_matters="Absorption at resistance is a warning sign of distribution. "
        "It often precedes a reversal.",
        intraday_relevance="Watch for high buying volume at resistance without price "
        "advancement. This indicates absorption.",
        failure_conditions="What looks like absorption could be genuine accumulation "
        "before a breakout. Context is critical.",
        related_observations=["absorption", "distribution", "resistance_rejection"],
    ),
    MarketPrinciple(
        principle_id="OF-004",
        name="Aggressive selling into support may be absorption",
        category=CategoryEnum.ORDER_FLOW,
        description="When price approaches support with heavy selling but fails to break, "
        "it may be smart money absorbing sell orders to accumulate.",
        why_it_matters="Absorption at support signals accumulation. "
        "It often precedes an upward move.",
        intraday_relevance="Watch for high selling volume at support without price decline. "
        "This indicates absorption.",
        failure_conditions="What looks like accumulation could be genuine distribution "
        "before a breakdown.",
        related_observations=["absorption", "accumulation", "support_rejection"],
    ),
    MarketPrinciple(
        principle_id="OF-005",
        name="OI expansion with compression can precede expansion",
        category=CategoryEnum.ORDER_FLOW,
        description="Rising open interest combined with price compression suggests "
        "position-building before an expansion move.",
        why_it_matters="OI tells you whether money is flowing into or out of the market. "
        "Compression + OI rise = explosive potential.",
        intraday_relevance="Monitor OI during range-bound periods. "
        "When OI expands while price compresses, prepare for directional expansion.",
        failure_conditions="OI data can be delayed and may not reflect spot-on-futures dynamics.",
        related_observations=["oi_increase", "compression", "volatility_expansion"],
    ),
    MarketPrinciple(
        principle_id="OF-006",
        name="Price-volume divergence warns of reversal",
        category=CategoryEnum.ORDER_FLOW,
        description="When price makes a new high/low but volume declines, "
        "it indicates weakening participation and potential reversal.",
        why_it_matters="Divergence between price and volume is one of the most reliable "
        "early warning signals for trend exhaustion.",
        intraday_relevance="Use RSI divergence combined with volume decline for higher "
        "confidence reversal signals.",
        failure_conditions="In strongly trending markets, volume divergence can persist "
        "without reversal.",
        related_observations=["bearish_divergence", "bullish_divergence", "volume_decline"],
    ),
]

VOLATILITY_PRINCIPLES = [
    MarketPrinciple(
        principle_id="VOL-001",
        name="Compression precedes expansion",
        category=CategoryEnum.VOLATILITY,
        description="Periods of low volatility (compression) are typically followed by "
        "periods of high volatility (expansion). Volatility is cyclical.",
        why_it_matters="Identifying compression helps anticipate upcoming expansion moves. "
        "The longer the compression, the more powerful the expansion.",
        intraday_relevance="Look for tightening ranges on low timeframes. "
        "A breakout from compression often produces a fast, sustained move.",
        failure_conditions="Compression can resolve in the opposite direction of expected. "
        "The timing of expansion is unpredictable.",
        related_observations=["tight_range", "squeeze", "volatility_expansion"],
    ),
    MarketPrinciple(
        principle_id="VOL-002",
        name="High volatility increases both opportunity and stop risk",
        category=CategoryEnum.VOLATILITY,
        description="In high-volatility environments, potential reward is larger but "
        "stops must be wider to avoid noise-induced exits.",
        why_it_matters="Stop placement must adapt to current volatility. "
        "Using a fixed stop size in variable volatility destroys edge.",
        intraday_relevance="Use ATR or average range to set dynamic stops. "
        "Reduce position size when volatility is elevated.",
        failure_conditions="Volatility can spike without warning, catching wide stops too.",
        related_observations=["high_atr", "volatility_spike", "wide_spread"],
    ),
    MarketPrinciple(
        principle_id="VOL-003",
        name="Volatility regime determines stop size",
        category=CategoryEnum.VOLATILITY,
        description="Stop loss distance should be proportional to current market volatility. "
        "Tight stops in high volatility lead to premature exits.",
        why_it_matters="Using volatility-adjusted stops improves win rate by avoiding "
        "noise-based stop-outs.",
        intraday_relevance="Use ATR-based stop placement. "
        "A stop at 1.5x to 2x ATR from entry is a common volatility-adjusted approach.",
        failure_conditions="Extreme volatility can blow through even wide stops during "
        "liquidation cascades.",
        related_observations=["atr_stop", "volatility_adjusted", "stop_hunt"],
    ),
    MarketPrinciple(
        principle_id="VOL-004",
        name="Low volatility with rising participation may signal preparation",
        category=CategoryEnum.VOLATILITY,
        description="When volatility is low but volume and OI are rising, "
        "informed participants may be building positions for an anticipated move.",
        why_it_matters="This is a warning that the quiet period may end soon with "
        "a directional expansion.",
        intraday_relevance="Monitor volume and OI alongside range contraction. "
        "When both rise during compression, prepare for a breakout.",
        failure_conditions="Position-building can precede a move in either direction. "
        "The direction is not knowable from these factors alone.",
        related_observations=["compression", "oi_increase", "volume_rise"],
    ),
    MarketPrinciple(
        principle_id="VOL-005",
        name="Volatility expansion without volume fades quickly",
        category=CategoryEnum.VOLATILITY,
        description="A sudden volatility spike on low volume is often a liquidity event "
        "(stop run, liquidation cascade) that fades rapidly.",
        why_it_matters="Not all volatility expansion is tradeable. "
        "Those without volume backing are traps.",
        intraday_relevance="When price makes a fast, wide-range move on low volume, "
        "expect reversion. Do not chase.",
        failure_conditions="News events can produce volatility expansion on low volume "
        "that does not reverse immediately.",
        related_observations=["volatility_spike", "low_volume_breakout", "liquidation_event"],
    ),
]

REGIME_PRINCIPLES = [
    MarketPrinciple(
        principle_id="REG-001",
        name="Strategies are regime-dependent",
        category=CategoryEnum.REGIME,
        description="No single strategy works in all market conditions. "
        "What works in trends fails in ranges, and vice versa.",
        why_it_matters="Forcing a strategy onto an incompatible regime destroys expectancy. "
        "Regime identification must precede strategy selection.",
        intraday_relevance="Classify the current intraday regime before considering any setup. "
        "Trending, ranging, choppy, and volatile regimes each require different approaches.",
        failure_conditions="Regime classification is probabilistic, not binary. "
        "A regime can change without clear warning.",
        related_observations=["regime_change", "trend_detection", "range_detection"],
    ),
    MarketPrinciple(
        principle_id="REG-002",
        name="Trend logic fails in chop",
        category=CategoryEnum.REGIME,
        description="Trend-following strategies in choppy, directionless markets "
        "produce repeated false signals and losses.",
        why_it_matters="Chop destroys trend systems. "
        "Recognizing chop and avoiding trend strategies preserves capital.",
        intraday_relevance="Use ADX, choppiness index, or price action structure "
        "to identify choppy conditions. When chop is detected, trend-following is no-trade.",
        failure_conditions="Chop can resolve into a trend. Early trend detection in chop "
        "can capture the breakout.",
        related_observations=["choppy_market", "adx_below_25", "range_bound"],
    ),
    MarketPrinciple(
        principle_id="REG-003",
        name="Mean reversion fails during expansion",
        category=CategoryEnum.REGIME,
        description="Mean reversion strategies that short extensions or buy dips "
        "fail catastrophically during strong directional expansion.",
        why_it_matters="Counter-trend trading during expansion has negative expectancy. "
        "Expansion markets require trend-following or patience.",
        intraday_relevance="When volatility is expanding and price is trending strongly, "
        "do not try to pick tops or bottoms.",
        failure_conditions="Even strong trends have pullbacks. Differentiating a pullback "
        "from a reversal is the challenge.",
        related_observations=["trending_market", "volatility_expansion", "strong_trend"],
    ),
    MarketPrinciple(
        principle_id="REG-004",
        name="Breakout logic fails without participation",
        category=CategoryEnum.REGIME,
        description="Breakouts that occur on low volume or without order-flow confirmation "
        "have a high failure rate.",
        why_it_matters="Not all breakouts are tradeable. "
        "Requiring confirmation saves capital from fakeouts.",
        intraday_relevance="Wait for volume expansion and price acceptance above/below "
        "the level before entering a breakout.",
        failure_conditions="Some breakouts happen so fast that waiting for confirmation "
        "sacrifices the entry.",
        related_observations=["low_volume_breakout", "volume_expansion", "fakeout"],
    ),
    MarketPrinciple(
        principle_id="REG-005",
        name="No-trade is a valid decision",
        category=CategoryEnum.REGIME,
        description="When market conditions are unclear, contradictory, or unfavorable, "
        "the correct decision is to not trade.",
        why_it_matters="Forcing trades in uncertain conditions destroys expectancy. "
        "Capital preservation means skipping low-quality setups.",
        intraday_relevance="If regime is unclear, if evidence conflicts, "
        "if confidence is below threshold — do not trade.",
        failure_conditions="Sitting out too long can miss opportunities. "
        "Balance between patience and participation is key.",
        related_observations=["uncertain_market", "conflicting_evidence", "low_confidence"],
    ),
    MarketPrinciple(
        principle_id="REG-006",
        name="Choppy markets destroy edge",
        category=CategoryEnum.REGIME,
        description="Markets without clear direction produce random outcomes. "
        "Even good systems lose money in chop due to slippage and false signals.",
        why_it_matters="Chop is a destroyer of edge. "
        "Identifying chop and reducing activity protects performance.",
        intraday_relevance="When price oscillates without purpose, reduce position size "
        "or stop trading entirely.",
        failure_conditions="Chop boundaries can lead to eventual breakouts. "
        "Trading range boundaries with tight stops can capture breakouts.",
        related_observations=["choppy_market", "range_bound", "mean_reversion"],
    ),
]

MANIPULATION_PRINCIPLES = [
    MarketPrinciple(
        principle_id="MAN-001",
        name="Fake breakouts trap late entries",
        category=CategoryEnum.MANIPULATION,
        description="Price briefly breaks a key level, triggering entry orders, "
        "then reverses sharply. This traps breakout traders on the wrong side.",
        why_it_matters="Most breakouts fail. Requiring confirmation before entry "
        "avoids fakeout traps.",
        intraday_relevance="Watch for breakouts that immediately reverse. "
        "A failed breakout is a strong signal for a move in the opposite direction.",
        failure_conditions="Real breakouts can also pull back to test the level "
        "before continuing, which looks like a fakeout initially.",
        related_observations=["fakeout", "failed_breakout", "wick_reclaim"],
    ),
    MarketPrinciple(
        principle_id="MAN-002",
        name="Stop hunts create false bearish signals",
        category=CategoryEnum.MANIPULATION,
        description="Price breaks below a support level to trigger long stops, "
        "then reverses back above. This creates a false bearish signal.",
        why_it_matters="A break below support that immediately reclaims is a liquidity grab, "
        "not a genuine breakdown.",
        intraday_relevance="When price breaks support but closes back above within "
        "a few candles, it is likely a stop hunt. Look for long entries.",
        failure_conditions="Genuine breakdowns also break support. "
        "Distinguishing a stop hunt from a real breakdown requires context.",
        related_observations=["stop_hunt", "liquidity_sweep", "false_breakdown"],
    ),
    MarketPrinciple(
        principle_id="MAN-003",
        name="Liquidity sweeps shake out weak hands before directional move",
        category=CategoryEnum.MANIPULATION,
        description="Price deliberately moves beyond obvious levels to trigger stops "
        "and shake out traders, then moves directionally.",
        why_it_matters="Liquidity sweeps provide fuel for the subsequent directional move. "
        "Identifying sweeps helps position before the move.",
        intraday_relevance="Look for wicks extending beyond key levels with rapid reclaim. "
        "This is often the launch point for a directional move.",
        failure_conditions="Not all sweeps precede directional moves. "
        "Some sweeps are followed by more consolidation.",
        related_observations=["liquidity_sweep", "wick_reclaim", "break_of_structure"],
    ),
    MarketPrinciple(
        principle_id="MAN-004",
        name="Long traps trap breakout buyers above resistance",
        category=CategoryEnum.MANIPULATION,
        description="Price breaks above resistance, attracting breakout buyers, "
        "then reverses sharply below. Long traders are trapped.",
        why_it_matters="Long traps are common at obvious resistance levels. "
        "They signal that smart money distributed positions at the high.",
        intraday_relevance="After a failed breakout above resistance, expect aggressive selling. "
        "Short entries at the reclaim level can be high probability.",
        failure_conditions="Genuine breakouts above resistance also show a pullback. "
        "Distinguishing a pullback from a trap requires volume context.",
        related_observations=["fakeout", "failed_breakout", "distribution"],
    ),
    MarketPrinciple(
        principle_id="MAN-005",
        name="Short traps trap breakout sellers below support",
        category=CategoryEnum.MANIPULATION,
        description="Price breaks below support, attracting breakout sellers, "
        "then reverses sharply above. Short traders are trapped.",
        why_it_matters="Short traps are common at obvious support levels. "
        "They signal that smart money accumulated positions at the low.",
        intraday_relevance="After a failed breakdown below support, expect aggressive buying. "
        "Long entries at the reclaim level can be high probability.",
        failure_conditions="Genuine breakdowns below support also show a pullback. "
        "Distinguishing a pullback from a trap requires volume context.",
        related_observations=["fakeout", "failed_breakdown", "accumulation"],
    ),
    MarketPrinciple(
        principle_id="MAN-006",
        name="Reclaim after sweep confirms manipulation",
        category=CategoryEnum.MANIPULATION,
        description="When price sweeps beyond a level and reclaims it with volume, "
        "it confirms that the sweep was a liquidity grab, not a genuine breakout.",
        why_it_matters="Reclaim confirmation provides a high-probability entry in the "
        "direction of the reversal.",
        intraday_relevance="Enter on confirmation of reclaim after a sweep. "
        "Use the sweep low/high as stop level.",
        failure_conditions="Reclaim can fail if the market has changed direction. "
        "Always use a stop loss.",
        related_observations=["wick_reclaim", "volume_confirmation", "stop_hunt"],
    ),
    MarketPrinciple(
        principle_id="MAN-007",
        name="Failed breakdown precedes reversal",
        category=CategoryEnum.MANIPULATION,
        description="A breakdown below support that immediately reverses and closes above "
        "the level often precedes an aggressive move higher.",
        why_it_matters="Failed breakdowns reveal that selling pressure was exhausted. "
        "The trapped sellers become fuel for the reversal.",
        intraday_relevance="After a failed breakdown, look for long entries "
        "with the swept low as invalidation.",
        failure_conditions="A failed breakdown can be followed by another breakdown "
        "attempt. Wait for confirmation.",
        related_observations=["failed_breakdown", "liquidity_sweep", "accumulation"],
    ),
    MarketPrinciple(
        principle_id="MAN-008",
        name="Failed breakout precedes reversal",
        category=CategoryEnum.MANIPULATION,
        description="A breakout above resistance that immediately reverses and closes below "
        "the level often precedes an aggressive move lower.",
        why_it_matters="Failed breakouts reveal that buying pressure was exhausted. "
        "The trapped buyers become fuel for the reversal.",
        intraday_relevance="After a failed breakout, look for short entries "
        "with the swept high as invalidation.",
        failure_conditions="A failed breakout can be followed by another breakout attempt. "
        "Wait for confirmation.",
        related_observations=["failed_breakout", "liquidity_sweep", "distribution"],
    ),
]

BEHAVIORAL_PRINCIPLES = [
    MarketPrinciple(
        principle_id="BEH-001",
        name="Fear and greed create poor positioning",
        category=CategoryEnum.BEHAVIORAL,
        description="Emotional extremes cause traders to enter late, exit early, "
        "or hold losing positions. Fear at lows and greed at highs create poor risk-reward.",
        why_it_matters="Recognizing emotional extremes in the market helps avoid "
        "the same mistakes. When sentiment is extreme, the opposite trade is often better.",
        intraday_relevance="Extreme fear at support (high volume selling) often marks a bottom. "
        "Extreme greed at resistance (high volume buying) often marks a top.",
        failure_conditions="Sentiment can stay extreme longer than expected. "
        "Extreme sentiment alone is not a timing signal.",
        related_observations=["capitulation", "euphoria", "volume_extreme"],
    ),
    MarketPrinciple(
        principle_id="BEH-002",
        name="Crowded trades become vulnerable",
        category=CategoryEnum.BEHAVIORAL,
        description="When too many traders are positioned on the same side, "
        "the trade becomes vulnerable to a sharp reversal.",
        why_it_matters="Crowded positions are targets for smart money. "
        "Monitoring positioning helps identify vulnerable trades.",
        intraday_relevance="Watch for extreme long/short ratios on exchanges. "
        "When a position is overwhelmingly crowded, the contrarian move is likely.",
        failure_conditions="Trends can continue despite extreme crowding. "
        "Positioning is one signal among many.",
        related_observations=["long_ratio_extreme", "funding_extreme", "positioning_unwind"],
    ),
    MarketPrinciple(
        principle_id="BEH-003",
        name="Funding extremes can reveal crowding",
        category=CategoryEnum.BEHAVIORAL,
        description="When funding rates reach extreme positive or negative values, "
        "it indicates extreme positioning on one side.",
        why_it_matters="Extreme funding often signals that a position is overcrowded "
        "and due for a unwind.",
        intraday_relevance="Monitor 8-hour funding rates. "
        "Extreme positive funding = too many longs = vulnerability. "
        "Extreme negative funding = too many shorts = potential bounce.",
        failure_conditions="Funding can remain extreme in strong trends. "
        "Trend + extreme funding = trend may continue until funding resets.",
        related_observations=["funding_extreme", "long_squeeze", "short_squeeze"],
    ),
    MarketPrinciple(
        principle_id="BEH-004",
        name="Late breakout chasers are weak hands",
        category=CategoryEnum.BEHAVIORAL,
        description="Traders who enter after a breakout has already run are late to the move. "
        "Their positions are weak and unwind quickly on any pullback.",
        why_it_matters="Identifying late entrants helps anticipate weakness. "
        "When late buyers are trapped, reversals can be violent.",
        intraday_relevance="After a strong move, if volume spikes but price stalls, "
        "late chasers may be buying. This often precedes a pullback.",
        failure_conditions="Strong trends can absorb late entrants and continue moving. "
        "Late entry alone is not a reversal signal.",
        related_observations=["volume_spike_stall", "late_entries", "weak_hands"],
    ),
    MarketPrinciple(
        principle_id="BEH-005",
        name="Retail positioning extremes are contrarian signals",
        category=CategoryEnum.BEHAVIORAL,
        description="When retail trader long/short ratios reach extremes, "
        "the market tends to move in the opposite direction.",
        why_it_matters="Retail traders tend to be wrong at turning points. "
        "Extreme retail positioning is a useful contrarian indicator.",
        intraday_relevance="Monitor retail long/short ratios on exchanges. "
        "When >80% of retail traders are long, be cautious of tops. "
        "When >80% are short, be cautious of bottoms.",
        failure_conditions="Retail can be right during strong trends. "
        "Contrarian positioning works best at regime turning points.",
        related_observations=["retail_ratio_extreme", "contrarian_setup", "positioning_unwind"],
    ),
]

PROBABILITY_PRINCIPLES = [
    MarketPrinciple(
        principle_id="PROB-001",
        name="No signal is certain",
        category=CategoryEnum.PROBABILITY,
        description="Every trading signal has a probability of failure, "
        "regardless of how strong it appears. Uncertainty is inherent.",
        why_it_matters="Accepting uncertainty prevents overconfidence and "
        "ensures proper risk management on every trade.",
        intraday_relevance="Even the highest-conviction intraday setup can fail. "
        "Always set a stop loss and size accordingly.",
        failure_conditions="None — this is a universal principle.",
        related_observations=["risk_management", "stop_loss", "position_sizing"],
    ),
    MarketPrinciple(
        principle_id="PROB-002",
        name="Confidence must be evidence-based",
        category=CategoryEnum.PROBABILITY,
        description="Confidence in a trade should be proportional to the quantity and "
        "quality of supporting evidence, not gut feeling.",
        why_it_matters="Evidence-based confidence improves decision quality and "
        "reduces emotional trading.",
        intraday_relevance="Before entering a trade, enumerate the evidence for and against. "
        "If evidence is thin, confidence should be low.",
        failure_conditions="False evidence (misinterpreted data) can create false confidence.",
        related_observations=["evidence_scoring", "confidence_calibration", "confirmation_bias"],
    ),
    MarketPrinciple(
        principle_id="PROB-003",
        name="Missing evidence increases uncertainty",
        category=CategoryEnum.PROBABILITY,
        description="When expected supporting evidence is absent, "
        "uncertainty about the trade outcome increases significantly.",
        why_it_matters="Trading without key confirming data is gambling. "
        "Waiting for evidence preserves capital.",
        intraday_relevance="If a setup requires order-flow confirmation and it is missing, "
        "do not enter. Missing evidence is a valid reason to skip.",
        failure_conditions="Waiting for too much evidence can cause missed entries. "
        "Balance between evidence requirements and opportunity cost is needed.",
        related_observations=["missing_confirmation", "uncertainty", "skip_trade"],
    ),
    MarketPrinciple(
        principle_id="PROB-004",
        name="Contradictions reduce trade quality",
        category=CategoryEnum.PROBABILITY,
        description="When evidence supports both directions, trade quality is degraded. "
        "Contradictions increase the probability of loss.",
        why_it_matters="High-quality trades have evidence supporting one direction. "
        "Contradictory evidence should reduce position size or cancel the trade.",
        intraday_relevance="If macro says bullish but order flow says bearish, "
        "uncertainty is high. Reduce size or skip.",
        failure_conditions="Contradictions can resolve with strong directional moves. "
        "They are not always negative.",
        related_observations=["mixed_signals", "conflicting_timeframes", "uncertainty"],
    ),
    MarketPrinciple(
        principle_id="PROB-005",
        name="Edge must survive fees, slippage, and funding",
        category=CategoryEnum.PROBABILITY,
        description="A strategy with 55% win rate and 2:1 RR may still lose money "
        "after fees, slippage, and funding costs are accounted for.",
        why_it_matters="Gross expectancy is not net expectancy. "
        "Transaction costs must be included in backtest results.",
        intraday_relevance="Futures trading incurs funding fees every 8 hours. "
        "A 6-hour hold may cross two funding periods. Model this in expectancy.",
        failure_conditions="None — this is a universal principle.",
        related_observations=["expectancy_calculation", "funding_cost", "slippage_model"],
    ),
]

RISK_PRINCIPLES = [
    MarketPrinciple(
        principle_id="RISK-001",
        name="Capital preservation comes before profit",
        category=CategoryEnum.RISK,
        description="The primary goal is to preserve trading capital. "
        "Profit is secondary. A trader who loses their capital cannot trade.",
        why_it_matters="Every trading decision should be evaluated first by "
        "'can I afford to lose this?' before 'how much can I make?'",
        intraday_relevance="Risk per trade should be a small fraction of account equity. "
        "Never risk more than 1-2% of capital on a single intraday trade.",
        failure_conditions="None — this is foundational to all trading.",
        related_observations=["position_sizing", "risk_per_trade", "stop_loss"],
    ),
    MarketPrinciple(
        principle_id="RISK-002",
        name="Forced trades destroy expectancy",
        category=CategoryEnum.RISK,
        description="Trading out of boredom, revenge, or pressure to make a trade "
        "produces negative expectancy outcomes.",
        why_it_matters="Forced trades are not evidence-based. They bypass the system's "
        "filters and reduce overall performance.",
        intraday_relevance="After a loss, do not immediately re-enter. "
        "After a winning streak, do not increase size impulsively.",
        failure_conditions="None — this is a behavioral risk principle.",
        related_observations=["revenge_trading", "boredom_trading", "fomo"],
    ),
    MarketPrinciple(
        principle_id="RISK-003",
        name="Daily drawdown limits are mandatory",
        category=CategoryEnum.RISK,
        description="A maximum daily loss limit stops trading for the day "
        "when losses exceed a threshold. This prevents catastrophic days.",
        why_it_matters="One bad day should not wipe out weeks of gains. "
        "Drawdown limits protect the account from emotional spirals.",
        intraday_relevance="Set a hard daily loss limit (e.g., 5-10% of account). "
        "When hit, stop trading for the day, no exceptions.",
        failure_conditions="None — hard limits should always be enforced.",
        related_observations=["daily_loss_limit", "kill_switch", "risk_management"],
    ),
    MarketPrinciple(
        principle_id="RISK-004",
        name="Position sizing must adapt to confidence and risk",
        category=CategoryEnum.RISK,
        description="Position size should be proportional to confidence level "
        "and inversely proportional to market risk.",
        why_it_matters="Fixed position sizing ignores the probabilistic nature of trading. "
        "Adaptive sizing improves risk-adjusted returns.",
        intraday_relevance="High-confidence setups with clear evidence get full allocation. "
        "Low-confidence or high-volatility setups get reduced size.",
        failure_conditions="Overconfidence can lead to oversized positions. "
        "System must cap maximum position size regardless of confidence.",
        related_observations=["position_sizing", "confidence_scoring", "risk_scoring"],
    ),
    MarketPrinciple(
        principle_id="RISK-005",
        name="A good system must skip bad markets",
        category=CategoryEnum.RISK,
        description="A complete trading system includes the ability to identify "
        "and skip unfavorable market conditions.",
        why_it_matters="Skipping bad markets is as important as trading good ones. "
        "A system that always trades has no filter.",
        intraday_relevance="When conditions are unclear, contradictory, or low-confidence, "
        "the system produces NO_TRADE decisions.",
        failure_conditions="Over-filtering can cause missed opportunities. "
        "Balance between skipping bad markets and participating in good ones.",
        related_observations=["no_trade", "market_filter", "skip_condition"],
    ),
    MarketPrinciple(
        principle_id="RISK-006",
        name="Reducing risk after loss protects the account",
        category=CategoryEnum.RISK,
        description="After taking a loss, reducing position size or taking a break "
        "protects capital from the revenge-trading spiral.",
        why_it_matters="Losses impair judgment. "
        "Reducing risk after a loss prevents the natural tendency to overtrade.",
        intraday_relevance="After a stop-out, reduce next trade size by 50% "
        "or wait for a clear high-confidence setup.",
        failure_conditions="None — this is a protective mechanism.",
        related_observations=["loss_sequence", "risk_reduction", "cool_off"],
    ),
]


def get_all_principles() -> list[MarketPrinciple]:
    return (
        AUCTION_PRINCIPLES
        + LIQUIDITY_PRINCIPLES
        + ORDERFLOW_PRINCIPLES
        + VOLATILITY_PRINCIPLES
        + REGIME_PRINCIPLES
        + MANIPULATION_PRINCIPLES
        + BEHAVIORAL_PRINCIPLES
        + PROBABILITY_PRINCIPLES
        + RISK_PRINCIPLES
    )


def get_all_categories() -> list[CategoryEnum]:
    return list(CategoryEnum)
