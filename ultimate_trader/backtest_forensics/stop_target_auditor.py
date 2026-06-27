from typing import Any

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class StopTargetAuditResult:
    def __init__(self):
        self.stop_quality_score: float = 100.0
        self.target_realism_score: float = 100.0
        self.stop_target_valid: bool = True
        self.warnings: list[str] = []
        self.recommended_fix: str = ""

    def add_warning(self, msg: str, penalty: float = 10.0):
        self.warnings.append(msg)
        self.stop_target_valid = False


class StopTargetAuditor:
    def audit(self, trade: TradeDiagnostics, atr: float = 0.0, candle_range: float = 0.0) -> StopTargetAuditResult:
        result = StopTargetAuditResult()

        if trade.stop_loss == 0 or trade.entry_price == 0:
            result.add_warning("No stop loss defined", 50.0)
            return result

        stop_dist = abs(trade.entry_price - trade.stop_loss)
        target_dist = abs(trade.target_price - trade.entry_price) if trade.target_price > 0 else 0.0
        stop_dist_pct = (stop_dist / trade.entry_price) * 100
        target_dist_pct = (target_dist / trade.entry_price) * 100 if trade.target_price > 0 else 0.0

        if trade.direction.value == "LONG":
            if trade.stop_loss >= trade.entry_price:
                result.add_warning("Stop loss above entry for LONG trade", 50.0)
            if trade.target_price <= trade.entry_price and trade.target_price > 0:
                result.add_warning("Target below entry for LONG trade", 50.0)
        else:
            if trade.stop_loss <= trade.entry_price:
                result.add_warning("Stop loss below entry for SHORT trade", 50.0)
            if trade.target_price >= trade.entry_price and trade.target_price > 0:
                result.add_warning("Target above entry for SHORT trade", 50.0)

        if atr > 0 and stop_dist > 0:
            stop_atr_ratio = stop_dist / atr
            if stop_atr_ratio < 0.3:
                result.add_warning(f"Stop too tight: {stop_dist_pct:.3f}% / ATR={atr:.2f} = {stop_atr_ratio:.2f}x ATR — within noise", 30.0)
                result.stop_quality_score = max(0, result.stop_quality_score - 30)
            elif stop_atr_ratio < 0.5:
                result.add_warning(f"Stop tight: {stop_atr_ratio:.2f}x ATR — may be inside normal noise", 15.0)
                result.stop_quality_score = max(0, result.stop_quality_score - 15)
            else:
                result.stop_quality_score = min(100, result.stop_quality_score + 10)

        if candle_range > 0 and stop_dist > 0:
            stop_range_ratio = stop_dist / candle_range
            if stop_range_ratio < 0.5:
                result.add_warning(f"Stop narrow relative to candle range: {stop_range_ratio:.2f}x", 10.0)

        if target_dist > 0 and atr > 0:
            target_atr_ratio = target_dist / atr
            if target_atr_ratio > 20:
                result.add_warning(f"Target too far: {target_atr_ratio:.1f}x ATR — may never reach", 25.0)
                result.target_realism_score = max(0, result.target_realism_score - 25)
            elif target_atr_ratio > 10:
                result.add_warning(f"Target ambitious: {target_atr_ratio:.1f}x ATR", 10.0)
                result.target_realism_score = max(0, result.target_realism_score - 10)
            else:
                result.target_realism_score = min(100, result.target_realism_score + 5)

        if target_dist > 0 and stop_dist > 0:
            rr = target_dist / stop_dist
            if rr > 10:
                result.add_warning(f"RR {rr:.1f}:1 — mathematically valid but practically unrealistic", 15.0)
            elif rr < 1.0:
                result.add_warning(f"RR {rr:.1f}:1 — reward less than risk", 30.0)

        if trade.exit_reason.value == "STOP_LOSS" and trade.holding_candles == 1:
            result.add_warning("Same-candle stop-first — stop hit on entry candle", 20.0)

        if not result.warnings:
            result.recommended_fix = "Stop and target appear reasonable"
        else:
            top_warning = result.warnings[0]
            if "tight" in top_warning.lower() or "noise" in top_warning.lower():
                result.recommended_fix = "Widen stop loss to at least 0.5–1.0x ATR to avoid noise stops"
            elif "far" in top_warning.lower() or "unrealistic" in top_warning.lower():
                result.recommended_fix = "Reduce target distance or increase holding time expectation"
            elif "inverted" in top_warning.lower():
                result.recommended_fix = "Fix inverted stop/target logic for direction"
            elif "RR" in top_warning:
                result.recommended_fix = "Adjust stop or target to achieve RR between 1.5 and 5"
            elif "candle" in top_warning.lower():
                result.recommended_fix = "Review entry zone — avoid stop too close to market noise on entry candle"

        return result
