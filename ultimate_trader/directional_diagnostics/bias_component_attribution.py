from collections import defaultdict
from typing import Any


class ComponentAttributionResult:
    def __init__(self):
        self.components_helping_direction: list[str] = []
        self.components_hurting_direction: list[str] = []
        self.unreliable_components: list[str] = []
        self.recommended_reweighting: str = ""
        self.components_to_disable_for_testing: list[str] = []


class BiasComponentAttribution:
    def analyze(self, trades: list[dict]) -> ComponentAttributionResult:
        result = ComponentAttributionResult()

        win_by_comp: dict[str, int] = defaultdict(int)
        total_by_comp: dict[str, int] = defaultdict(int)

        for t in trades:
            components = t.get("directional_components", {})
            is_winner = t.get("is_winner", False)
            for comp, val in components.items():
                if isinstance(val, (int, float)) and val != 0:
                    total_by_comp[comp] += 1
                    if is_winner:
                        win_by_comp[comp] += 1

        for comp in sorted(total_by_comp.keys()):
            total = total_by_comp[comp]
            wins = win_by_comp.get(comp, 0)
            wr = (wins / total * 100) if total > 0 else 0.0

            if wr >= 50:
                result.components_helping_direction.append(comp)
            elif wr >= 40:
                result.components_helping_direction.append(f"{comp} (weak)")
            elif wr >= 30:
                result.components_hurting_direction.append(comp)
            else:
                result.components_hurting_direction.append(f"{comp} (harmful)")

        if result.components_hurting_direction:
            result.unreliable_components = [c.split(" (")[0] for c in result.components_hurting_direction]
            result.recommended_reweighting = (
                f"Reduce weight of: {', '.join(result.unreliable_components[:3])}. "
                f"Consider disabling for A/B testing."
            )
            result.components_to_disable_for_testing = result.unreliable_components[:3]
        else:
            result.recommended_reweighting = "All components appear directionally reliable"

        return result

    def attribute(self, audits) -> ComponentAttributionResult:
        from ultimate_trader.directional_diagnostics.bias_auditor import DirectionalBiasAudit

        trades = []
        for a in audits:
            comps = {}
            if a.lsm_bias:
                comps["lsm_bias"] = 1.0 if a.lsm_bias.upper() in ("LONG", "BULLISH") else -1.0
            if a.microstructure_bias:
                comps["microstructure_bias"] = 1.0 if a.microstructure_bias.upper() in ("LONG", "BULLISH") else -1.0
            if a.orderflow_bias:
                comps["orderflow_bias"] = 1.0 if a.orderflow_bias.upper() in ("LONG", "BULLISH") else -1.0
            trades.append({
                "directional_components": comps,
                "net_r": a.net_r,
                "direction": a.direction_taken,
                "is_winner": a.outcome.value == "WIN",
            })
        return self.analyze(trades)
