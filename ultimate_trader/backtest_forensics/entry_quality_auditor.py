from typing import Any

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class EntryQualityResult:
    def __init__(self):
        self.entry_quality_score: float = 100.0
        self.entry_safe: bool = True
        self.warnings: list[str] = []
        self.recommended_fix: str = ""

    def add_entry_warning(self, msg: str, penalty: float = 10.0):
        self.warnings.append(msg)
        self.entry_quality_score = max(0, self.entry_quality_score - penalty)
        self.entry_safe = False


class EntryQualityAuditor:
    def audit(self, trade: TradeDiagnostics, atr: float = 0.0, candle_range: float = 0.0) -> EntryQualityResult:
        result = EntryQualityResult()

        if trade.entry_price == 0:
            result.add_entry_warning("No entry price recorded", 50.0)
            return result

        stop_dist = abs(trade.entry_price - trade.stop_loss) if trade.stop_loss > 0 else 0
        entry_to_stop_pct = (stop_dist / trade.entry_price) * 100 if trade.entry_price > 0 and stop_dist > 0 else 0

        if trade.direction.value == "LONG":
            if trade.entry_price >= trade.target_price > 0:
                result.add_entry_warning("Entry price already at or above target for LONG", 40.0)
        else:
            if trade.entry_price <= trade.target_price > 0:
                result.add_entry_warning("Entry price already at or below target for SHORT", 40.0)

        if atr > 0 and stop_dist > 0:
            entry_atr = stop_dist / atr
            if entry_atr < 0.2:
                result.add_entry_warning(f"Entry too close to invalidation: {entry_atr:.2f}x ATR", 25.0)

        if candle_range > 0 and stop_dist > 0:
            entry_range = stop_dist / candle_range
            if entry_range < 0.3:
                result.add_entry_warning(f"Entry-to-stop distance ({entry_range:.2f}x range) — too tight", 15.0)

        if trade.max_adverse_excursion_r > 0 and trade.max_favorable_excursion_r == 0:
            result.add_entry_warning("Entry triggered immediately into adverse candle movement", 20.0)

        if trade.holding_candles == 1 and trade.exit_reason.value == "STOP_LOSS":
            result.add_entry_warning("Entry zone triggered stop-loss on same candle — poor entry timing", 30.0)

        if trade.entry_to_stop_distance_percent > 0 and trade.entry_to_stop_distance_percent < 0.1:
            result.add_entry_warning(f"Entry zone too narrow: {trade.entry_to_stop_distance_percent:.3f}%", 10.0)

        if not result.warnings:
            result.recommended_fix = "Entry quality appears acceptable"
        else:
            if "invalidation" in result.warnings[0].lower():
                result.recommended_fix = "Increase distance from entry to stop to reduce noise-triggered exits"
            elif "adverse" in result.warnings[0].lower():
                result.recommended_fix = "Wait for confirmation candle before entering"
            elif "target" in result.warnings[0].lower():
                result.recommended_fix = "Do not enter when price has already reached target zone"
            elif "timing" in result.warnings[0].lower() or "candle" in result.warnings[0].lower():
                result.recommended_fix = "Widen entry zone or use limit entries instead of market-on-close"
            elif "narrow" in result.warnings[0].lower():
                result.recommended_fix = "Widen entry zone to allow for normal slippage and spread"

        return result



