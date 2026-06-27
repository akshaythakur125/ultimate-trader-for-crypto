_ACTION_RANK = {"ALLOW": 0, "HUMAN_REVIEW": 1, "BLOCK": 2}


class DirectionConflictResult:
    def __init__(self):
        self.has_conflict: bool = False
        self.severity: str = "NONE"
        self.conflict_reasons: list[str] = []
        self.recommended_action: str = "ALLOW"


class DirectionConflictDetector:
    def _set_action(self, result, action: str):
        if _ACTION_RANK.get(action, 0) > _ACTION_RANK.get(result.recommended_action, 0):
            result.recommended_action = action

    def detect(
        self,
        lsm_bias: str = "",
        microstructure_bias: str = "",
        orderflow_bias: str = "",
        strategy_bias: str = "",
    ) -> DirectionConflictResult:
        result = DirectionConflictResult()

        biases = [
            ("LSM", lsm_bias.upper()),
            ("Microstructure", microstructure_bias.upper()),
            ("Orderflow", orderflow_bias.upper()),
            ("Strategy", strategy_bias.upper()),
        ]
        long_count = sum(1 for _, b in biases if b in ("LONG", "BULLISH"))
        short_count = sum(1 for _, b in biases if b in ("SHORT", "BEARISH"))
        neutral_count = sum(1 for _, b in biases if b in ("", "NEUTRAL", "BALANCED"))

        total_voting = long_count + short_count
        if total_voting == 0:
            result.conflict_reasons.append("No directional bias available")
            result.recommended_action = "HUMAN_REVIEW"
            return result

        if long_count > 0 and short_count > 0:
            conflict_ratio = min(long_count, short_count) / max(long_count, short_count)
            if conflict_ratio >= 0.5:
                result.has_conflict = True
                result.severity = "HIGH"
                sources_long = [s for s, b in biases if b in ("LONG", "BULLISH")]
                sources_short = [s for s, b in biases if b in ("SHORT", "BEARISH")]
                result.conflict_reasons.append(f"DIRECTION CONFLICT: {', '.join(sources_long)} say LONG vs {', '.join(sources_short)} say SHORT")
                self._set_action(result, "BLOCK")
            elif conflict_ratio >= 0.25:
                result.has_conflict = True
                result.severity = "MODERATE"
                result.conflict_reasons.append("Moderate directional conflict detected")
                self._set_action(result, "HUMAN_REVIEW")

        if orderflow_bias.upper() in ("LONG", "BULLISH") and microstructure_bias.upper() in ("SHORT", "BEARISH"):
            result.has_conflict = True
            result.severity = "HIGH"
            result.conflict_reasons.append("Bullish absorption but bearish microstructure")
            self._set_action(result, "HUMAN_REVIEW")
        elif orderflow_bias.upper() in ("SHORT", "BEARISH") and microstructure_bias.upper() in ("LONG", "BULLISH"):
            result.has_conflict = True
            result.severity = "HIGH"
            result.conflict_reasons.append("Bearish absorption but bullish microstructure")
            self._set_action(result, "HUMAN_REVIEW")

        if not result.conflict_reasons:
            result.recommended_action = "ALLOW"

        return result
