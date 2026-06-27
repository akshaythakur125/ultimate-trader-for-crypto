"""
Market microstructure concepts for intraday crypto futures trading.

These concepts describe how markets function at the tick-and-order level.
They are not principles but contextual knowledge used by the reasoning engine.
"""

from pydantic import BaseModel, Field


class MicrostructureConcept(BaseModel):
    name: str
    description: str
    intraday_significance: str


MICROSTRUCTURE_CONCEPTS = [
    MicrostructureConcept(
        name="Order book depth",
        description="The cumulative volume of limit orders at each price level. "
        "Depth reveals potential support and resistance zones.",
        intraday_significance="Thin depth means price can move easily. "
        "Thick depth may act as a magnet or barrier.",
    ),
    MicrostructureConcept(
        name="Bid-ask spread",
        description="The difference between the best bid and best ask. "
        "Spread widens during low liquidity and narrows during high liquidity.",
        intraday_significance="Wide spread increases slippage cost. "
        "Avoid trading during wide-spread conditions or adjust expectancy.",
    ),
    MicrostructureConcept(
        name="Order book imbalance",
        description="The ratio of bid volume to ask volume in the order book. "
        "Imbalance suggests near-term directional bias.",
        intraday_significance="Strong bid-side imbalance suggests support. "
        "Strong ask-side imbalance suggests resistance.",
    ),
    MicrostructureConcept(
        name="Trade tape (time & sales)",
        description="The sequential record of every executed trade. "
        "Shows whether trades are aggressive (market orders) or passive (limit orders).",
        intraday_significance="Aggressive buying indicates conviction. "
        "Passive orders may indicate accumulation or distribution.",
    ),
    MicrostructureConcept(
        name="Cumulative delta",
        description="The running total of aggressive buys minus aggressive sells. "
        "Rising delta = buying pressure. Falling delta = selling pressure.",
        intraday_significance="Delta divergence from price warns of reversal. "
        "Delta confirmation supports trend continuation.",
    ),
    MicrostructureConcept(
        name="Iceberg orders",
        description="Large hidden orders that show only a small portion in the book. "
        "Used by institutions to hide their true size.",
        intraday_significance="Repeated fills at the same level may indicate an iceberg. "
        "These levels become significant support/resistance.",
    ),
    MicrostructureConcept(
        name="Spoofing",
        description="Placing large orders with no intention of execution "
        "to create false impressions of supply or demand.",
        intraday_significance="Large orders that repeatedly appear and disappear "
        "may be spoofing. Treat such levels with caution.",
    ),
    MicrostructureConcept(
        name="Quote stuffing",
        description="Rapid submission and cancellation of orders to create confusion "
        "or slow down competing algorithms.",
        intraday_significance="High-frequency quote changes during quiet periods "
        "may signal manipulation. Avoid trading in such conditions.",
    ),
    MicrostructureConcept(
        name="Liquidation cascade",
        description="When falling price triggers long liquidations, which accelerate "
        "the fall, triggering more liquidations. A self-reinforcing cycle.",
        intraday_significance="Liquidation cascades create rapid, violent moves. "
        "They often end as quickly as they start, creating snap-back opportunities.",
    ),
]
