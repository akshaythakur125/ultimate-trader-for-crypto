from ultimate_trader.signal_engine.trade_plan import RiskRewardAnalysis


class RRAnalyzer:
    MINIMUM_RR = 3.0
    PREFERRED_RR = 5.0

    def analyze(
        self,
        entry_price: float,
        stop_loss_price: float,
        target_price: float,
    ) -> RiskRewardAnalysis:
        risk = abs(entry_price - stop_loss_price)
        reward = abs(target_price - entry_price)

        rr_ratio = reward / risk if risk > 0 else 0.0

        meets_min = rr_ratio >= self.MINIMUM_RR
        meets_pref = rr_ratio >= self.PREFERRED_RR

        summary_parts = []
        if rr_ratio >= self.PREFERRED_RR:
            summary_parts.append(f"Excellent R:R ({rr_ratio:.1f}:1)")
        elif rr_ratio >= self.MINIMUM_RR:
            summary_parts.append(f"Adequate R:R ({rr_ratio:.1f}:1)")
        else:
            summary_parts.append(f"Below minimum R:R ({rr_ratio:.1f}:1)")

        if not meets_min:
            summary_parts.append("— REJECTED")
        elif not meets_pref and rr_ratio >= self.MINIMUM_RR:
            summary_parts.append("— meets minimum, below preferred")

        return RiskRewardAnalysis(
            rr_id="RR-ANALYSIS",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            risk_per_unit=round(risk, 8),
            reward_per_unit=round(reward, 8),
            rr_ratio=round(rr_ratio, 4),
            meets_minimum_rr=meets_min,
            meets_preferred_rr=meets_pref,
            rr_summary=" ".join(summary_parts),
        )

    def meets_minimum(self, rr_ratio: float) -> bool:
        return rr_ratio >= self.MINIMUM_RR
