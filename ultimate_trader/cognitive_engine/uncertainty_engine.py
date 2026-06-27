from typing import Optional

from ultimate_trader.cognitive_engine.observation import Observation, ObservationType


class UncertaintyResult:
    def __init__(
        self,
        score: float = 50.0,
        factors: Optional[list[str]] = None,
    ) -> None:
        self.score = score
        self.factors = factors or []

    def __repr__(self) -> str:
        return f"UncertaintyResult(score={self.score:.1f}, factors={len(self.factors)})"


class UncertaintyEngine:
    def assess_uncertainty(
        self,
        observations: Optional[list[Observation]] = None,
        contradictions: Optional[list[dict]] = None,
        missing_evidence: Optional[list[str]] = None,
    ) -> UncertaintyResult:
        score = 0.0
        factors: list[str] = []

        obs = observations or []
        contradictions_list = contradictions or []
        missing = missing_evidence or []

        if not obs:
            score += 30.0
            factors.append("No observations available")

        data_missing = self._check_data_missing(obs)
        score += data_missing["score"]
        factors.extend(data_missing["factors"])

        evidence_conflict = self._check_evidence_conflict(contradictions_list)
        score += evidence_conflict["score"]
        factors.extend(evidence_conflict["factors"])

        regime_unclear = self._check_regime_unclear(obs)
        score += regime_unclear["score"]
        factors.extend(regime_unclear["factors"])

        vol_abnormal = self._check_volatility_abnormal(obs)
        score += vol_abnormal["score"]
        factors.extend(vol_abnormal["factors"])

        thin_liquidity = self._check_thin_liquidity(obs)
        score += thin_liquidity["score"]
        factors.extend(thin_liquidity["factors"])

        flow_missing = self._check_orderflow_missing(obs)
        score += flow_missing["score"]
        factors.extend(flow_missing["factors"])

        if len(missing) > 0:
            score += min(len(missing) * 5.0, 20.0)
            factors.append(f"Missing evidence: {', '.join(missing[:3])}")

        score = min(score, 100.0)
        return UncertaintyResult(score=round(score, 1), factors=factors)

    def _check_data_missing(
        self, observations: list[Observation]
    ) -> dict:
        score = 0.0
        factors: list[str] = []
        if not observations:
            return {"score": 0.0, "factors": []}
        observed_types = {o.observation_type for o in observations}
        expected = {
            ObservationType.PRICE_ACTION,
            ObservationType.VOLUME,
        }
        missing = expected - observed_types
        if missing:
            score = len(missing) * 5.0
            for m in missing:
                factors.append(f"Missing {m.value.lower()} data")
        return {"score": score, "factors": factors}

    def _check_evidence_conflict(
        self, contradictions: list[dict]
    ) -> dict:
        score = 0.0
        factors: list[str] = []
        for c in contradictions:
            severity = c.get("severity", "LOW")
            if severity == "HIGH":
                score += 15.0
            elif severity == "MEDIUM":
                score += 8.0
            else:
                score += 3.0
            factors.append(f"Contradiction: {c.get('rule', 'unknown')}")
        return {"score": score, "factors": factors}

    def _check_regime_unclear(
        self, observations: list[Observation]
    ) -> dict:
        score = 0.0
        factors: list[str] = []
        for o in observations:
            if o.observation_type == ObservationType.REGIME:
                if "unclear" in o.description.lower():
                    score += 10.0
                    factors.append("Market regime is unclear")
        return {"score": score, "factors": factors}

    def _check_volatility_abnormal(
        self, observations: list[Observation]
    ) -> dict:
        score = 0.0
        factors: list[str] = []
        for o in observations:
            if o.observation_type == ObservationType.VOLATILITY:
                if "spike" in o.description.lower():
                    score += 8.0
                    factors.append("Volatility spike detected")
                if "expanding" in o.description.lower():
                    score += 5.0
                    factors.append("Volatility expanding")
        return {"score": score, "factors": factors}

    def _check_thin_liquidity(
        self, observations: list[Observation]
    ) -> dict:
        score = 0.0
        factors: list[str] = []
        for o in observations:
            if o.observation_type == ObservationType.LIQUIDITY:
                if "thin" in o.description.lower():
                    score += 10.0
                    factors.append("Thin liquidity increases uncertainty")
        return {"score": score, "factors": factors}

    def _check_orderflow_missing(
        self, observations: list[Observation]
    ) -> dict:
        score = 0.0
        factors: list[str] = []
        has_flow = any(
            o.observation_type == ObservationType.ORDER_FLOW
            for o in observations
        )
        if not has_flow:
            score += 8.0
            factors.append("Order flow confirmation absent")
        return {"score": score, "factors": factors}
