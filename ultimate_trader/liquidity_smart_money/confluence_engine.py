from collections import Counter
from typing import Optional

from ultimate_trader.liquidity_smart_money.models import (
    ConfluenceResult,
    DirectionalBias,
    Displacement,
    FVG,
    LiquidityZone,
    OrderBlock,
    PremiumDiscountState,
    StructureEvent,
    StructureType,
    Sweep,
    TradePermission,
)


_VOTE_WEIGHTS = {
    "liquidity": 3,
    "market_structure": 2,
    "fvg": 2,
    "order_block": 2,
    "premium_discount": 2,
    "displacement": 2,
    "orderflow": 2,
    "microstructure": 1,
}


class ConfluenceEngine:
    def __init__(self):
        self._result: Optional[ConfluenceResult] = None

    def analyze(
        self,
        liquidity_zones: list[LiquidityZone],
        sweeps: list[Sweep],
        structure_events: list[StructureEvent],
        fvgs: list[FVG],
        order_blocks: list[OrderBlock],
        premium_discount: Optional[PremiumDiscountState],
        displacements: list[Displacement],
        orderflow_bias: Optional[str] = None,
        microstructure_bias: Optional[str] = None,
    ) -> ConfluenceResult:

        breakdown: dict[str, float] = {}
        reasons_for: list[str] = []
        reasons_against: list[str] = []

        votes: dict[str, str] = {}
        scores: dict[str, float] = {}

        liquidity_score, liq_dir = self._score_liquidity(liquidity_zones, sweeps)
        breakdown["liquidity"] = liquidity_score
        scores["liquidity"] = liquidity_score
        if liq_dir != "NEUTRAL":
            votes["liquidity"] = liq_dir
            reasons_for.append(f"Liquidity alignment: {liq_dir.lower()} side pools/sweeps")

        structure_score, struct_dir = self._score_structure(structure_events)
        breakdown["market_structure"] = structure_score
        scores["market_structure"] = structure_score
        if struct_dir != "NEUTRAL":
            votes["market_structure"] = struct_dir
            reasons_for.append(f"Market structure: {struct_dir.lower()} bias")

        fvg_score, fvg_dir = self._score_fvg(fvgs)
        breakdown["fvg"] = fvg_score
        scores["fvg"] = fvg_score
        if fvg_dir != "NEUTRAL":
            votes["fvg"] = fvg_dir
            reasons_for.append(f"FVG alignment: {fvg_dir.lower()}")

        ob_score, ob_dir = self._score_order_blocks(order_blocks)
        breakdown["order_block"] = ob_score
        scores["order_block"] = ob_score
        if ob_dir != "NEUTRAL":
            votes["order_block"] = ob_dir
            reasons_for.append(f"Order block: {ob_dir.lower()} bias")

        pd_score, pd_dir = self._score_premium_discount(premium_discount)
        breakdown["premium_discount"] = pd_score
        scores["premium_discount"] = pd_score
        if pd_dir != "NEUTRAL":
            votes["premium_discount"] = pd_dir
            reasons_for.append(f"Premium/discount: in {pd_dir.lower()} zone")

        disp_score, disp_dir = self._score_displacement(displacements)
        breakdown["displacement"] = disp_score
        scores["displacement"] = disp_score
        if disp_dir != "NEUTRAL":
            votes["displacement"] = disp_dir
            reasons_for.append(f"Displacement: {disp_dir.lower()}")

        if orderflow_bias:
            of_dir = "NEUTRAL"
            if orderflow_bias in ("BUYER_AGGRESSION",):
                of_dir = "LONG"
            elif orderflow_bias in ("SELLER_AGGRESSION",):
                of_dir = "SHORT"
            of_score = 15.0 if of_dir != "NEUTRAL" else 0.0
            breakdown["orderflow"] = of_score
            scores["orderflow"] = of_score
            if of_dir != "NEUTRAL":
                votes["orderflow"] = of_dir
                reasons_for.append(f"Order flow: {orderflow_bias.lower()}")

        if microstructure_bias:
            ms_score = 10.0 if microstructure_bias in ("LONG", "SHORT") else 0.0
            breakdown["microstructure"] = ms_score
            scores["microstructure"] = ms_score
            if microstructure_bias in ("LONG", "SHORT"):
                votes["microstructure"] = microstructure_bias
                reasons_for.append(f"Microstructure: {microstructure_bias.lower()}")

        total = sum(breakdown.values())
        score = round(min(total, 100), 2)

        bias, directional_confidence, conflict_score, reason_dir = self._determine_bias(votes, scores)
        reversal_risk_score = self._compute_reversal_risk(sweeps, premium_discount, displacements)
        continuation_score = self._compute_continuation(structure_events, displacements, votes)

        reasons_against = self._collect_risks(
            sweeps, structure_events, fvgs, order_blocks, premium_discount, displacements
        )

        permission = self._determine_permission(score, conflict_score, reasons_against, bias)

        self._result = ConfluenceResult(
            confluence_score=score,
            directional_bias=bias,
            directional_confidence=directional_confidence,
            reversal_risk_score=reversal_risk_score,
            continuation_score=continuation_score,
            conflict_score=conflict_score,
            reason_for_direction=reason_dir,
            trade_permission=permission.value,
            reasons_for=reasons_for,
            reasons_against=reasons_against,
            confluence_breakdown=breakdown,
        )
        return self._result

    def _score_liquidity(self, zones: list[LiquidityZone], sweeps: list[Sweep]) -> tuple[float, str]:
        score = 0.0
        direction = "NEUTRAL"
        active_sweeps = [s for s in sweeps if s.has_reclaim]
        if active_sweeps:
            score += 25.0
            sweep_dirs = [s.sweep_type for s in active_sweeps]
            if any("BUY" in s for s in sweep_dirs):
                direction = "SHORT"
            if any("SELL" in s for s in sweep_dirs):
                direction = "LONG"
            if any("BUY" in s for s in sweep_dirs) and any("SELL" in s for s in sweep_dirs):
                direction = "NEUTRAL"
        active_zones = [z for z in zones if not z.is_swept and z.strength >= 1.5]
        if active_zones:
            score += min(len(active_zones) * 5, 15.0)
        return score, direction

    def _score_structure(self, events: list[StructureEvent]) -> tuple[float, str]:
        score = 0.0
        direction = "NEUTRAL"
        for evt in events[-5:]:
            if evt.structure_type in (StructureType.BOS, StructureType.CHOCH):
                score += 20.0
                direction = "LONG" if evt.direction == "BULLISH" else ("SHORT" if evt.direction == "BEARISH" else direction)
            elif evt.structure_type == StructureType.COMPRESSION:
                score += 10.0
            elif evt.structure_type == StructureType.TREND_CONTINUATION:
                score += 10.0
                direction = "LONG" if evt.direction == "BULLISH" else ("SHORT" if evt.direction == "BEARISH" else direction)
        return score, direction

    def _score_fvg(self, fvgs: list[FVG]) -> tuple[float, str]:
        score = 0.0
        direction = "NEUTRAL"
        active = [f for f in fvgs if not f.is_filled and not f.is_mitigated]
        for fvg in active:
            if fvg.gap_size > 5:
                score += 20.0
                direction = "LONG" if fvg.fvg_type == "BULLISH_FVG" else ("SHORT" if fvg.fvg_type == "BEARISH_FVG" else direction)
            elif fvg.gap_size > 2:
                score += 12.0
                direction = direction or ("LONG" if fvg.fvg_type == "BULLISH_FVG" else "SHORT")
            else:
                score += 6.0
        return min(score, 30), direction

    def _score_order_blocks(self, blocks: list[OrderBlock]) -> tuple[float, str]:
        score = 0.0
        direction = "NEUTRAL"
        active = [b for b in blocks if not b.is_mitigated and not b.is_invalidated]
        for ob in active:
            if ob.strength_score >= 70:
                score += 20.0
                direction = "LONG" if ob.ob_type == "BULLISH_OB" else ("SHORT" if ob.ob_type == "BEARISH_OB" else direction)
            elif ob.strength_score >= 40:
                score += 12.0
            else:
                score += 5.0
        cutoff = 5
        if len(active) > cutoff:
            score = min(score, 30)
        return min(score, 30), direction

    def _score_premium_discount(self, pd: Optional[PremiumDiscountState]) -> tuple[float, str]:
        if not pd:
            return 0.0, "NEUTRAL"
        if pd.current_price_zone == "DISCOUNT":
            return 15.0, "LONG"
        if pd.current_price_zone == "PREMIUM":
            return 15.0, "SHORT"
        return 5.0, "NEUTRAL"

    def _score_displacement(self, displacements: list[Displacement]) -> tuple[float, str]:
        score = 0.0
        direction = "NEUTRAL"
        for d in displacements[-3:]:
            if d.is_displaced and d.displacement_type in ("STRONG", "AFTER_SWEEP", "VOLUME_SUPPORTED"):
                score += 15.0
                direction = "LONG" if d.direction == "UP" else "SHORT"
        return min(score, 20), direction

    def _determine_bias(
        self, votes: dict[str, str], scores: dict[str, float]
    ) -> tuple[DirectionalBias, float, float, str]:
        if not votes:
            return DirectionalBias.NEUTRAL, 0.0, 0.0, "No directional votes from any component"

        weighted_long = 0.0
        weighted_short = 0.0

        for component, direction in votes.items():
            weight = _VOTE_WEIGHTS.get(component, 1)
            comp_score = scores.get(component, 0)
            if direction == "LONG":
                weighted_long += weight * (1 + comp_score / 100)
            elif direction == "SHORT":
                weighted_short += weight * (1 + comp_score / 100)

        total_weight = weighted_long + weighted_short
        if total_weight == 0:
            return DirectionalBias.NEUTRAL, 0.0, 0.0, "No weighted direction"

        long_share = weighted_long / total_weight
        short_share = weighted_short / total_weight
        conflict_score = 1.0 - abs(long_share - short_share)

        bias = DirectionalBias.NEUTRAL
        directional_confidence = 0.0
        reason = ""

        if long_share > short_share and conflict_score < 0.6:
            bias = DirectionalBias.LONG
            directional_confidence = long_share
            long_voters = [k for k, v in votes.items() if v == "LONG"]
            reason = f"LONG ({len(long_voters)} components, conf={directional_confidence:.0%})"
        elif short_share > long_share and conflict_score < 0.6:
            bias = DirectionalBias.SHORT
            directional_confidence = short_share
            short_voters = [k for k, v in votes.items() if v == "SHORT"]
            reason = f"SHORT ({len(short_voters)} components, conf={directional_confidence:.0%})"

        if conflict_score >= 0.6:
            long_voters = [k for k, v in votes.items() if v == "LONG"]
            short_voters = [k for k, v in votes.items() if v == "SHORT"]
            reason = f"CONFLICT ({len(long_voters)}L vs {len(short_voters)}S, conflict={conflict_score:.0%})"

        return bias, round(directional_confidence, 2), round(conflict_score, 2), reason

    def _compute_reversal_risk(
        self,
        sweeps: list[Sweep],
        premium_discount: Optional[PremiumDiscountState],
        displacements: list[Displacement],
    ) -> float:
        risk = 0.0
        active_sweeps = [s for s in sweeps if s.has_reclaim]
        if active_sweeps:
            risk += 20.0
        failed_sweeps = [s for s in sweeps if s.is_failed]
        if failed_sweeps:
            risk += 15.0
        if premium_discount:
            if premium_discount.current_price_zone == "PREMIUM":
                risk += 10.0
            elif premium_discount.current_price_zone == "DISCOUNT":
                risk += 10.0
        fake_displacements = [d for d in displacements if d.displacement_type == "FAKE"]
        if fake_displacements:
            risk += 10.0
        return min(risk, 100)

    def _compute_continuation(
        self,
        structure_events: list[StructureEvent],
        displacements: list[Displacement],
        votes: dict[str, str],
    ) -> float:
        score = 0.0
        for evt in structure_events[-5:]:
            if evt.structure_type in (StructureType.BOS, StructureType.CHOCH, StructureType.TREND_CONTINUATION):
                score += 15.0
        for d in displacements[-3:]:
            if d.is_displaced and d.displacement_type in ("STRONG", "VOLUME_SUPPORTED"):
                score += 10.0
        if len(votes) >= 3:
            dirs = list(votes.values())
            if len(set(dirs)) == 1 and dirs[0] != "NEUTRAL":
                score += 20.0
        return min(score, 100)

    def _collect_risks(
        self,
        sweeps: list[Sweep],
        structure_events: list[StructureEvent],
        fvgs: list[FVG],
        order_blocks: list[OrderBlock],
        premium_discount: Optional[PremiumDiscountState],
        displacements: list[Displacement],
    ) -> list[str]:
        risks: list[str] = []
        failed_sweeps = [s for s in sweeps if s.is_failed]
        if failed_sweeps:
            risks.append(f"Failed sweep detected: {failed_sweeps[-1].description}")
        failure_events = [e for e in structure_events if e.structure_type == StructureType.STRUCTURE_FAILURE]
        if failure_events:
            risks.append("Structure failure detected — market contracting")
        fvg_filled = [f for f in fvgs if f.is_filled]
        if fvg_filled:
            risks.append("FVG filled — potential reversal zone")
        ob_invalidated = [b for b in order_blocks if b.is_invalidated]
        if ob_invalidated:
            risks.append("Order block invalidated")
        if premium_discount:
            if premium_discount.current_price_zone == "PREMIUM":
                risks.append("Price in premium zone — risky for longs")
            elif premium_discount.current_price_zone == "DISCOUNT":
                risks.append("Price in discount zone — risky for shorts")
        fake_displacements = [d for d in displacements if d.displacement_type == "FAKE"]
        if fake_displacements:
            risks.append("Fake displacement detected")
        return risks

    def _determine_permission(
        self, score: float, conflict_score: float, risks: list[str], bias: DirectionalBias
    ) -> TradePermission:
        if conflict_score >= 0.6:
            return TradePermission.BLOCK
        if score < 20:
            return TradePermission.BLOCK
        if len(risks) >= 3:
            return TradePermission.CAUTION
        if bias == DirectionalBias.NEUTRAL and score < 50:
            return TradePermission.BLOCK
        if score < 40:
            return TradePermission.CAUTION
        return TradePermission.ALLOW

    def get_result(self) -> Optional[ConfluenceResult]:
        return self._result

    def reset(self):
        self._result = None
