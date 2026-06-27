from typing import Optional

from ultimate_trader.microstructure_engine.models import (
    AbsorptionSignal,
    AbsorptionState,
    OrderBookSnapshot,
)


class AbsorptionDetector:
    def __init__(
        self,
        absorption_ratio_threshold: float = 0.7,
        history_length: int = 10,
        price_move_threshold_percent: float = 0.05,
    ):
        self.absorption_ratio_threshold = absorption_ratio_threshold
        self.history_length = history_length
        self.price_move_threshold_percent = price_move_threshold_percent
        self._history: list[OrderBookSnapshot] = []

    def analyze(self, snapshot: OrderBookSnapshot) -> AbsorptionSignal:
        self._history.append(snapshot)
        if len(self._history) > self.history_length:
            self._history.pop(0)

        if len(self._history) < 3:
            return AbsorptionSignal(detected=False)

        mid_price = snapshot.mid_price
        if mid_price <= 0:
            return AbsorptionSignal(detected=False)

        bid_pressure = self._compute_aggressive_pressure(snapshot.bids, "bid")
        ask_pressure = self._compute_aggressive_pressure(snapshot.asks, "ask")

        if bid_pressure["high"] and not ask_pressure["high"]:
            level_price = self._find_nearest_resistance(mid_price)
            if level_price and self._price_stuck(mid_price):
                return AbsorptionSignal(
                    detected=True,
                    absorption_type="BUYING_ABSORBED_AT_RESISTANCE",
                    level_price=level_price,
                    strength="MEDIUM",
                    description=(
                        f"Aggressive buying detected near {level_price:.2f} "
                        "but price not advancing — absorption likely"
                    ),
                )

        if ask_pressure["high"] and not bid_pressure["high"]:
            level_price = self._find_nearest_support(mid_price)
            if level_price and self._price_stuck(mid_price):
                return AbsorptionSignal(
                    detected=True,
                    absorption_type="SELLING_ABSORBED_AT_SUPPORT",
                    level_price=level_price,
                    strength="MEDIUM",
                    description=(
                        f"Aggressive selling detected near {level_price:.2f} "
                        "but price not declining — absorption likely"
                    ),
                )

        return AbsorptionSignal(detected=False)

    def reset(self):
        self._history.clear()

    def _compute_aggressive_pressure(self, levels: list, side: str) -> dict:
        if not levels:
            return {"high": False, "ratio": 0.0}
        top_levels = levels[:3]
        if not top_levels:
            return {"high": False, "ratio": 0.0}
        top_qty = sum(l.quantity for l in top_levels)
        total_qty = sum(l.quantity for l in levels)
        ratio = top_qty / total_qty if total_qty > 0 else 0.0
        return {"high": ratio > self.absorption_ratio_threshold, "ratio": ratio}

    def _find_nearest_resistance(self, price: float) -> Optional[float]:
        if not self._history:
            return None
        recent = self._history[-1]
        resistances = [a.price for a in recent.asks if a.price > price * 1.001]
        return min(resistances) if resistances else None

    def _find_nearest_support(self, price: float) -> Optional[float]:
        if not self._history:
            return None
        recent = self._history[-1]
        supports = [b.price for b in recent.bids if b.price < price * 0.999]
        return max(supports) if supports else None

    def _price_stuck(self, current_mid: float) -> bool:
        if len(self._history) < 3:
            return False
        prices = [s.mid_price for s in self._history[-3:] if s.mid_price > 0]
        if len(prices) < 2:
            return False
        max_move = max(prices) - min(prices)
        max_move_percent = (max_move / current_mid) * 100 if current_mid > 0 else 0
        return max_move_percent < self.price_move_threshold_percent
