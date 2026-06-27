from enum import Enum
from typing import Optional

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics, ExitReason


class FailureCategory(str, Enum):
    STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
    TARGET_TOO_AMBITIOUS = "TARGET_TOO_AMBITIOUS"
    BAD_ENTRY = "BAD_ENTRY"
    WRONG_DIRECTION = "WRONG_DIRECTION"
    CHOP_MARKET = "CHOP_MARKET"
    LATE_SIGNAL = "LATE_SIGNAL"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    SAME_CANDLE_STOP_FIRST = "SAME_CANDLE_STOP_FIRST"
    OVERTRADING_CLUSTER = "OVERTRADING_CLUSTER"
    SIMULATOR_LOGIC_ISSUE = "SIMULATOR_LOGIC_ISSUE"
    UNKNOWN = "UNKNOWN"


class FailureClassification:
    def __init__(self):
        self.category: FailureCategory = FailureCategory.UNKNOWN
        self.confidence: float = 0.0
        self.explanation: str = ""
        self.fix_suggestion: str = ""


class FailureClassifier:
    def classify(self, trade: TradeDiagnostics) -> FailureClassification:
        result = FailureClassification()

        if trade.exit_reason == ExitReason.STOP_LOSS and trade.holding_candles == 0:
            result.category = FailureCategory.SIMULATOR_LOGIC_ISSUE
            result.confidence = 0.9
            result.explanation = "Trade stopped on same candle as entry with 0 holding time — likely simulator logic error"
            result.fix_suggestion = "Review entry fill logic: entry and stop should not trigger on same tick"
            return result

        if trade.exit_reason == ExitReason.STOP_LOSS and trade.holding_candles <= 1:
            result.category = FailureCategory.SAME_CANDLE_STOP_FIRST
            result.confidence = 0.85
            result.explanation = f"Stop hit within 1 candle of entry (holding={trade.holding_candles})"
            result.fix_suggestion = "Widen entry zone or use limit orders; check if stop is inside natural spread"
            return result

        if trade.exit_reason == ExitReason.EXPIRY:
            result.category = FailureCategory.CHOP_MARKET
            result.confidence = 0.5
            result.explanation = "Trade expired without hitting stop or target — range-bound market"
            result.fix_suggestion = "Reduce holding time or avoid low-volatility regimes"
            return result

        if trade.entry_to_stop_distance_percent > 0 and trade.entry_to_stop_distance_percent < 0.1:
            result.category = FailureCategory.STOP_TOO_TIGHT
            result.confidence = 0.85
            result.explanation = f"Stop distance is only {trade.entry_to_stop_distance_percent:.3f}% — inside normal noise"
            result.fix_suggestion = "Widen stop to at least 0.5x ATR"
            return result

        if trade.max_favorable_excursion_r >= 1.0 and trade.net_r <= 0:
            result.category = FailureCategory.TARGET_TOO_AMBITIOUS
            result.confidence = 0.8
            result.explanation = f"Reached {trade.max_favorable_excursion_r:.1f}R but stopped out — target too far"
            result.fix_suggestion = "Reduce target distance or trail stop after favorable movement"
            return result

        if trade.max_favorable_excursion_r >= trade.rr_ratio * 0.8 and trade.net_r <= 0 and trade.rr_ratio > 0:
            result.category = FailureCategory.TARGET_TOO_AMBITIOUS
            result.confidence = 0.75
            result.explanation = f"Reached {trade.max_favorable_excursion_r:.1f}R ({trade.max_favorable_excursion_r/trade.rr_ratio*100:.0f}% of target) but reversed"
            result.fix_suggestion = "Reduce target or trail stop to lock partial profits"
            return result

        if trade.max_adverse_excursion_r > 0 and trade.max_favorable_excursion_r == 0:
            result.category = FailureCategory.BAD_ENTRY
            result.confidence = 0.75
            result.explanation = "Price moved against immediately on entry — never favorable"
            result.fix_suggestion = "Check entry timing; consider waiting for confirmation candle"
            return result

        if trade.exit_reason == ExitReason.STOP_LOSS and trade.net_r <= -1.0:
            result.category = FailureCategory.WRONG_DIRECTION
            result.confidence = 0.6
            result.explanation = f"Loss of {trade.net_r:.1f}R suggests opposite direction was correct"
            result.fix_suggestion = "Check market structure alignment before entry"
            return result

        result.category = FailureCategory.UNKNOWN
        result.confidence = 0.3
        result.explanation = f"Trade lost {trade.net_r:.1f}R (exit: {trade.exit_reason.value})"
        result.fix_suggestion = "Review full diagnostics for pattern"
        return result
