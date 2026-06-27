from ultimate_trader.directional_diagnostics.bias_auditor import BiasAuditor
from ultimate_trader.directional_diagnostics.bias_component_attribution import BiasComponentAttribution
from ultimate_trader.directional_diagnostics.direction_conflict_detector import DirectionConflictDetector


class DirectionalReplayReport:
    @classmethod
    def generate(
        cls,
        original_result: dict,
        inverted_result: dict,
        weak_blocked_result: dict,
        attribution_result,
        bias_summary,
        overtrading_reduced: bool = False,
    ) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("DIRECTIONAL DIAGNOSTIC REPORT")
        lines.append("=" * 70)

        lines.append("\n--- Original Direction ---")
        lines.append(f"  Trades:          {original_result.get('total_trades', 0)}")
        lines.append(f"  Win rate:        {original_result.get('win_rate', 0):.1f}%")
        lines.append(f"  Expectancy:      {original_result.get('expectancy', 0):.2f}R")
        lines.append(f"  Profit factor:   {original_result.get('profit_factor', 0):.2f}")
        lines.append(f"  Avg trades/day:  {original_result.get('avg_trades_per_day', 0):.1f}")

        lines.append("\n--- Inverted Direction ---")
        lines.append(f"  Trades:          {inverted_result.get('total_trades', 0)}")
        lines.append(f"  Win rate:        {inverted_result.get('win_rate', 0):.1f}%")
        lines.append(f"  Expectancy:      {inverted_result.get('expectancy', 0):.2f}R")
        lines.append(f"  Profit factor:   {inverted_result.get('profit_factor', 0):.2f}")
        lines.append(f"  Avg trades/day:  {inverted_result.get('avg_trades_per_day', 0):.1f}")

        lines.append("\n--- Weak Direction Blocked ---")
        lines.append(f"  Trades:          {weak_blocked_result.get('total_trades', 0)}")
        lines.append(f"  Win rate:        {weak_blocked_result.get('win_rate', 0):.1f}%")
        lines.append(f"  Expectancy:      {weak_blocked_result.get('expectancy', 0):.2f}R")
        lines.append(f"  Profit factor:   {weak_blocked_result.get('profit_factor', 0):.2f}")
        lines.append(f"  Avg trades/day:  {weak_blocked_result.get('avg_trades_per_day', 0):.1f}")

        lines.append("\n--- Component Attribution ---")
        if attribution_result:
            if attribution_result.components_helping_direction:
                lines.append(f"  Best:  {', '.join(attribution_result.components_helping_direction[:5])}")
            if attribution_result.components_hurting_direction:
                lines.append(f"  Worst: {', '.join(attribution_result.components_hurting_direction[:5])}")
            if attribution_result.unreliable_components:
                lines.append(f"  Unreliable: {', '.join(attribution_result.unreliable_components[:5])}")
            lines.append(f"  {attribution_result.recommended_reweighting}")

        lines.append("\n--- Bias Audit ---")
        if bias_summary:
            lines.append(f"  {bias_summary.audit_summary}")

        lines.append("\n--- Overtrading Status ---")
        if overtrading_reduced:
            lines.append("  Trade frequency control ACTIVE — overtrading reduced")
        else:
            lines.append("  Trade frequency control NOT applied in this test")

        lines.append("\n--- Final Recommendation ---")
        orig_ev = original_result.get("expectancy", 0)
        inv_ev = inverted_result.get("expectancy", 0)
        weak_ev = weak_blocked_result.get("expectancy", 0)

        if inv_ev > orig_ev and inv_ev > weak_ev:
            lines.append("  RECOMMENDATION: INVERT_DIRECTION_FOR_TESTING_ONLY")
            lines.append(f"  Inverted direction improves expectancy from {orig_ev:.2f}R to {inv_ev:.2f}R")
        elif weak_ev > orig_ev and weak_ev > inv_ev:
            lines.append("  RECOMMENDATION: BLOCK_WEAK_DIRECTION")
            lines.append(f"  Blocking weak direction improves expectancy from {orig_ev:.2f}R to {weak_ev:.2f}R")
        elif attribution_result and attribution_result.unreliable_components:
            lines.append("  RECOMMENDATION: REWEIGHT_COMPONENTS")
            lines.append(f"  Disable unreliable components: {', '.join(attribution_result.components_to_disable_for_testing[:3])}")
        elif attribution_result and attribution_result.components_to_disable_for_testing:
            lines.append("  RECOMMENDATION: DISABLE_UNRELIABLE_COMPONENTS")
        else:
            lines.append("  RECOMMENDATION: KEEP_DIRECTION")
            lines.append("  No directional inversion is justified. Improve stop/target placement instead.")

        lines.append("=" * 70)
        return "\n".join(lines)
