from typing import Any, Optional

from ultimate_trader.cognitive_engine.hypothesis_reasoning import (
    AlternativeHypothesis,
    HypothesisDirection,
)
from ultimate_trader.cognitive_engine.observation import Observation, ObservationType
from ultimate_trader.market_brain.knowledge_base import MarketKnowledgeBase

_ContradictionRule = dict[str, Any]


class ContradictionDetector:
    def __init__(self, kb: Optional[MarketKnowledgeBase] = None) -> None:
        self.kb = kb
        self.rules: list[_ContradictionRule] = self._build_rules()

    def _build_rules(self) -> list[_ContradictionRule]:
        return [
            {
                "name": "bullish_price_bearish_flow",
                "description": (
                    "Bullish price action but bearish order flow "
                    "— directional conflict."
                ),
                "check": self._check_price_flow_conflict,
            },
            {
                "name": "breakout_no_volume",
                "description": (
                    "Breakout or directional idea lacking volume "
                    "participation — move may be weak."
                ),
                "check": self._check_breakout_no_volume,
            },
            {
                "name": "long_high_manipulation_risk",
                "description": (
                    "Long directional hypothesis with high manipulation "
                    "risk — trap possible."
                ),
                "check": self._check_long_manipulation,
            },
            {
                "name": "trend_in_chop_regime",
                "description": (
                    "Trend-following hypothesis in choppy regime "
                    "— strategy mismatch."
                ),
                "check": self._check_trend_in_chop,
            },
            {
                "name": "high_confidence_missing_evidence",
                "description": (
                    "Confidence is high but critical evidence is missing "
                    "— overconfidence risk."
                ),
                "check": self._check_confidence_evidence_gap,
            },
            {
                "name": "good_rr_unrealistic_target",
                "description": (
                    "Claimed RR is good but target appears unrealistic "
                    "given volatility context."
                ),
                "check": self._check_rr_vs_volatility,
            },
        ]

    def _check_price_flow_conflict(
        self,
        observations: list[Observation],
        hypotheses: list[AlternativeHypothesis],
    ) -> Optional[_ContradictionRule]:
        has_bullish = any(
            h.direction_bias in (HypothesisDirection.LONG,)
            for h in hypotheses
        )
        has_bearish_flow = any(
            o.observation_type == ObservationType.ORDER_FLOW
            and "bearish" in o.description.lower()
            for o in observations
        )
        if has_bullish and has_bearish_flow:
            return self.rules[0]
        return None

    def _check_breakout_no_volume(
        self,
        observations: list[Observation],
        hypotheses: list[AlternativeHypothesis],
    ) -> Optional[_ContradictionRule]:
        has_directional = any(
            h.direction_bias in (HypothesisDirection.LONG, HypothesisDirection.SHORT)
            for h in hypotheses
        )
        has_volume_observation = any(
            o.observation_type == ObservationType.VOLUME for o in observations
        )
        if has_directional and not has_volume_observation:
            return self.rules[1]
        return None

    def _check_long_manipulation(
        self,
        observations: list[Observation],
        hypotheses: list[AlternativeHypothesis],
    ) -> Optional[_ContradictionRule]:
        has_long = any(
            h.direction_bias == HypothesisDirection.LONG for h in hypotheses
        )
        has_manipulation_risk = any(
            o.observation_type == ObservationType.LIQUIDITY
            and any(kw in o.description.lower() for kw in ["trap", "fakeout", "manipulation"])
            for o in observations
        )
        if has_long and has_manipulation_risk:
            return self.rules[2]
        return None

    def _check_trend_in_chop(
        self,
        observations: list[Observation],
        hypotheses: list[AlternativeHypothesis],
    ) -> Optional[_ContradictionRule]:
        has_trend = any(
            "trend" in h.name.lower() for h in hypotheses
        )
        has_chop = any(
            o.observation_type == ObservationType.REGIME
            and any(kw in o.description.lower() for kw in ["chop", "range", "no_trade"])
            for o in observations
        )
        if has_trend and has_chop:
            return self.rules[3]
        return None

    def _check_confidence_evidence_gap(
        self,
        observations: list[Observation],
        hypotheses: list[AlternativeHypothesis],
    ) -> Optional[_ContradictionRule]:
        for h in hypotheses:
            if h.confidence_score > 70 and len(h.supporting_observations) <= 1:
                return self.rules[4]
        return None

    def _check_rr_vs_volatility(
        self,
        observations: list[Observation],
        hypotheses: list[AlternativeHypothesis],
    ) -> Optional[_ContradictionRule]:
        return None

    def detect_all(
        self,
        observations: list[Observation],
        hypotheses: list[AlternativeHypothesis],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        for rule in self.rules:
            check_fn = rule["check"]
            result = check_fn(observations, hypotheses)
            if result is not None:
                contradictions.append(
                    {
                        "rule": result["name"],
                        "description": result["description"],
                        "severity": self._assess_severity(result["name"]),
                    }
                )
        return contradictions

    def _assess_severity(self, rule_name: str) -> str:
        high_severity = {"trend_in_chop_regime", "long_high_manipulation_risk"}
        medium_severity = {
            "bullish_price_bearish_flow",
            "high_confidence_missing_evidence",
        }
        if rule_name in high_severity:
            return "HIGH"
        if rule_name in medium_severity:
            return "MEDIUM"
        return "LOW"
