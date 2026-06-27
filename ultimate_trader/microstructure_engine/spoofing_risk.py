from typing import Optional

from ultimate_trader.microstructure_engine.models import (
    OrderBookSnapshot,
    SpoofingRiskLevel,
    SpoofingSignal,
)


class SpoofingRiskDetector:
    def __init__(
        self,
        history_length: int = 10,
        wall_disappear_threshold: float = 0.5,
        imbalance_change_threshold: float = 0.3,
    ):
        self.history_length = history_length
        self.wall_disappear_threshold = wall_disappear_threshold
        self.imbalance_change_threshold = imbalance_change_threshold
        self._history: list[OrderBookSnapshot] = []

    def analyze(self, snapshot: OrderBookSnapshot) -> SpoofingSignal:
        self._history.append(snapshot)
        if len(self._history) > self.history_length:
            self._history.pop(0)

        if len(self._history) < 3:
            return SpoofingSignal(detected=False, risk_level=SpoofingRiskLevel.NONE)

        wall_flash = self._detect_wall_flashing()
        imbalance_instability = self._detect_imbalance_instability()
        fake_wall = self._detect_fake_walls()

        reasons = []
        signals = 0

        if wall_flash:
            signals += 1
            reasons.append("large walls appearing and disappearing")
        if imbalance_instability:
            signals += 1
            reasons.append("imbalance unstable over recent snapshots")
        if fake_wall:
            signals += 2
            reasons.append("suspicious wall placement detected")

        risk = self._classify_risk(signals)
        detected = risk != SpoofingRiskLevel.NONE

        return SpoofingSignal(
            detected=detected,
            risk_level=risk,
            reason=" | ".join(reasons) if reasons else "No spoofing indicators detected",
        )

    def reset(self):
        self._history.clear()

    def _detect_wall_flashing(self) -> bool:
        if len(self._history) < 3:
            return False
        recent = self._history[-3:]
        bid_wall_counts = []
        ask_wall_counts = []
        for snap in recent:
            bid_walls = [l for l in snap.bids if l.quantity >= 200]
            ask_walls = [l for l in snap.asks if l.quantity >= 200]
            bid_wall_counts.append(len(bid_walls))
            ask_wall_counts.append(len(ask_walls))
        max_change_bid = max(bid_wall_counts) - min(bid_wall_counts)
        max_change_ask = max(ask_wall_counts) - min(ask_wall_counts)
        return max_change_bid >= 2 or max_change_ask >= 2

    def _detect_imbalance_instability(self) -> bool:
        if len(self._history) < 4:
            return False
        recent = self._history[-4:]
        imbalances = []
        for snap in recent:
            total = snap.bid_depth + snap.ask_depth
            if total > 0:
                imbalances.append(abs(snap.bid_depth - snap.ask_depth) / total)
        if len(imbalances) < 2:
            return False
        max_change = max(imbalances) - min(imbalances)
        return max_change > self.imbalance_change_threshold

    def _detect_fake_walls(self) -> bool:
        if len(self._history) < 4:
            return False
        mid = len(self._history) // 2
        first_half = self._history[:mid]
        second_half = self._history[mid:]
        if not first_half or not second_half:
            return False
        first_walls = self._count_wall_levels(first_half)
        second_walls = self._count_wall_levels(second_half)
        avg_first = first_walls / len(first_half)
        avg_second = second_walls / len(second_half)
        if avg_first == 0:
            return False
        change_ratio = abs(avg_second - avg_first) / avg_first
        return change_ratio > self.wall_disappear_threshold

    def _classify_risk(self, signal_count: int) -> SpoofingRiskLevel:
        if signal_count >= 3:
            return SpoofingRiskLevel.HIGH
        if signal_count == 2:
            return SpoofingRiskLevel.MEDIUM
        if signal_count == 1:
            return SpoofingRiskLevel.LOW
        return SpoofingRiskLevel.NONE

    def _count_wall_levels(self, snapshots: list[OrderBookSnapshot]) -> int:
        count = 0
        for snap in snapshots:
            for l in snap.bids:
                if l.quantity >= 200:
                    count += 1
            for l in snap.asks:
                if l.quantity >= 200:
                    count += 1
        return count
