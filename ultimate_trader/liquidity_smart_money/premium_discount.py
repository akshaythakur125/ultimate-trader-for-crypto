from typing import Optional

from ultimate_trader.liquidity_smart_money.models import (
    Candle,
    PremiumDiscountState,
    SwingPoint,
)


class PremiumDiscountEngine:
    def __init__(self):
        self._state: Optional[PremiumDiscountState] = None

    def analyze(
        self, swing_highs: list[SwingPoint], swing_lows: list[SwingPoint], current_price: float
    ) -> PremiumDiscountState:
        if not swing_highs or not swing_lows:
            dr_high = max((s.price for s in swing_highs), default=current_price * 1.01)
            dr_low = min((s.price for s in swing_lows), default=current_price * 0.99)
        else:
            dr_high = max(s.price for s in swing_highs)
            dr_low = min(s.price for s in swing_lows)

        if dr_high - dr_low < 0.001:
            dr_high = current_price * 1.01
            dr_low = current_price * 0.99

        equilibrium = (dr_high + dr_low) / 2
        premium_high = dr_high
        premium_low = equilibrium
        discount_high = equilibrium
        discount_low = dr_low

        ote_high = dr_high - (dr_high - dr_low) * 0.3
        ote_low = dr_high - (dr_high - dr_low) * 0.2

        zone = "EQUILIBRIUM"
        if current_price >= premium_low and current_price <= premium_high:
            zone = "PREMIUM"
        elif current_price <= discount_high and current_price >= discount_low:
            zone = "DISCOUNT"

        self._state = PremiumDiscountState(
            dealing_range_high=round(dr_high, 2),
            dealing_range_low=round(dr_low, 2),
            equilibrium=round(equilibrium, 2),
            premium_zone_high=round(premium_high, 2),
            premium_zone_low=round(premium_low, 2),
            discount_zone_high=round(discount_high, 2),
            discount_zone_low=round(discount_low, 2),
            optimal_entry_high=round(ote_high, 2),
            optimal_entry_low=round(ote_low, 2),
            current_price_zone=zone,
        )
        return self._state

    def get_state(self) -> Optional[PremiumDiscountState]:
        return self._state

    def reset(self):
        self._state = None
