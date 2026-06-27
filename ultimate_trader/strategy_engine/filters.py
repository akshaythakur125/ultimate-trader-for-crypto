from typing import Any, Optional

from ultimate_trader.historical_replay.models import HistoricalCandle, TradeDirection
from ultimate_trader.strategy_engine.models import FilterResult, StrategyConfig, StrategyContext


def _ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    multiplier = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * multiplier + ema
    return ema


def _atr(candles: list[HistoricalCandle], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    tr_values = []
    for i in range(1, period + 1):
        high = candles[-i].high
        low = candles[-i].low
        prev_close = candles[-i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)
    multiplier = 2.0 / (period + 1)
    atr_val = sum(tr_values) / period
    for v in tr_values:
        atr_val = (v - atr_val) * multiplier + atr_val
    return atr_val


def _sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


class TrendFilter:
    name = "trend"
    description = "HTF EMA structure alignment"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        closes = [c.close for c in ctx.candles_history]
        if len(closes) < max(config.ema_periods):
            return FilterResult(filter_name=self.name, passed=False, score=0.0, data_available=False, reasoning=["Not enough data for EMAs"])

        directions: list[str] = []
        for period in config.ema_periods:
            ema_val = _ema(closes, period)
            if ema_val is None:
                continue
            if ctx.candle.close > ema_val:
                directions.append("bullish")
            else:
                directions.append("bearish")

        target_dir = "bullish" if ctx.direction == TradeDirection.LONG else "bearish"
        aligned = sum(1 for d in directions if d == target_dir)
        opposed = len(directions) - aligned

        if aligned == len(directions):
            score = 100.0
            passed = True
            reasoning = [f"All {len(directions)} EMAs aligned with {ctx.direction.value} direction"]
        elif aligned >= len(directions) * 0.6:
            score = 60.0 + (aligned / len(directions)) * 40.0
            passed = True
            reasoning = [f"{aligned}/{len(directions)} EMAs aligned with {ctx.direction.value}"]
        elif aligned >= opposed:
            score = 40.0 + (aligned / len(directions)) * 20.0
            passed = score >= 50.0
            reasoning = [f"Weak alignment: {aligned}/{len(directions)} EMAs support {ctx.direction.value}"]
        else:
            score = max(0.0, (aligned / len(directions)) * 30.0)
            passed = False
            reasoning = [f"Trend opposes: {opposed}/{len(directions)} EMAs oppose {ctx.direction.value}"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.15), reasoning=reasoning,
        )


class StructureFilter:
    name = "structure"
    description = "Market structure BOS/CHOCH alignment"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        events = ctx.lsm_structure_events
        if not events:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["No structure events available"])

        last_event = events[-1]
        event_dir = getattr(last_event, "direction", "").upper()
        event_type = getattr(last_event, "structure_type", "")

        target_bullish = ctx.direction == TradeDirection.LONG
        aligns = False

        if event_dir in ("BULLISH", "LONG"):
            aligns = target_bullish
        elif event_dir in ("BEARISH", "SHORT"):
            aligns = not target_bullish

        if aligns:
            score = 90.0
            passed = True
            reasoning = [f"Last structure event ({event_type}) aligns: {event_dir}"]
        else:
            score = 20.0
            passed = False
            reasoning = [f"Structure opposes: last event was {event_type}/{event_dir}"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.12), reasoning=reasoning,
        )


class SweepFilter:
    name = "sweep"
    description = "Liquidity sweep confirmation"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        sweeps = ctx.lsm_sweeps
        if not sweeps:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["No sweeps detected"])

        recent_sweeps = [s for s in sweeps if getattr(s, "index", 0) >= len(ctx.candles_history) - 10]
        if not recent_sweeps:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=True, reasoning=["No recent sweeps within 10 candles"])

        target_type = "BUY_SIDE_SWEEP" if ctx.direction == TradeDirection.LONG else "SELL_SIDE_SWEEP"
        matching = [s for s in recent_sweeps if getattr(s, "sweep_type", "") == target_type]

        if matching:
            has_reclaim = any(getattr(s, "has_reclaim", False) for s in matching)
            score = 90.0 if has_reclaim else 70.0
            passed = True
            reasoning = [f"{len(matching)} {target_type} sweep(s) detected"]
            if has_reclaim:
                reasoning.append("With reclaim confirmation")
        else:
            score = 30.0
            passed = False
            reasoning = [f"No {target_type} sweeps detected"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.10), reasoning=reasoning,
        )


class FvgFilter:
    name = "fvg"
    description = "Fair Value Gap alignment"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        fvgs = ctx.lsm_fvgs
        if not fvgs:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["No FVGs detected"])

        target_type = "BULLISH_FVG" if ctx.direction == TradeDirection.LONG else "BEARISH_FVG"
        matching = [f for f in fvgs if getattr(f, "fvg_type", "") == target_type and \
                    not getattr(f, "is_mitigated", False) and not getattr(f, "is_filled", False)]

        if matching:
            recent = [f for f in matching if getattr(f, "index", 0) >= len(ctx.candles_history) - 20]
            score = 80.0 if recent else 60.0
            passed = True
            src = "recent" if recent else "existing"
            reasoning = [f"{len(matching)} active {target_type} FVG(s) available ({src})"]
        else:
            score = 40.0
            passed = False
            reasoning = [f"No active {target_type} FVGs"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.08), reasoning=reasoning,
        )


class OrderBlockFilter:
    name = "order_block"
    description = "Order Block alignment"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        obs = ctx.lsm_order_blocks
        if not obs:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["No order blocks detected"])

        target_type = "BULLISH_OB" if ctx.direction == TradeDirection.LONG else "BEARISH_OB"
        matching = [o for o in obs if getattr(o, "ob_type", "") == target_type and \
                    not getattr(o, "is_mitigated", False) and not getattr(o, "is_invalidated", False)]

        if matching:
            strong = [o for o in matching if getattr(o, "strength_score", 0) >= 50]
            score = 85.0 if strong else 65.0
            passed = True
            reasoning = [f"{len(matching)} active {target_type} OB(s)"]
            if strong:
                reasoning.append(f"{len(strong)} with strong score")
        else:
            score = 35.0
            passed = False
            reasoning = [f"No active {target_type} order blocks"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.08), reasoning=reasoning,
        )


class VolumeFilter:
    name = "volume"
    description = "Volume confirmation"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        volumes = [c.volume for c in ctx.candles_history]
        if len(volumes) < config.volume_lookback + 1:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["Not enough volume history"])

        avg_volume = sum(volumes[-config.volume_lookback:-1]) / (config.volume_lookback - 1)
        current_vol = ctx.candle.volume
        ratio = current_vol / avg_volume if avg_volume > 0 else 1.0

        if ratio >= 1.5:
            score = 90.0
            passed = True
            reasoning = [f"Volume {ratio:.2f}x average — strong confirmation"]
        elif ratio >= config.min_volume_ratio:
            score = 60.0 + (ratio - config.min_volume_ratio) * 50.0
            passed = True
            reasoning = [f"Volume {ratio:.2f}x average — moderate"]
        else:
            score = max(0.0, ratio / config.min_volume_ratio * 40.0)
            passed = False
            reasoning = [f"Volume {ratio:.2f}x average — below {config.min_volume_ratio}x threshold"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.08), reasoning=reasoning,
        )


class OrderflowFilter:
    name = "orderflow"
    description = "Order-flow confirmation"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        if ctx.orderflow_data is None:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["Orderflow data not available — skipped"])

        return FilterResult(
            filter_name=self.name, passed=True, score=50.0,
            weight=config.weights.get(self.name, 0.10),
            reasoning=["Orderflow data available but analysis not fully integrated"],
        )


class FundingFilter:
    name = "funding"
    description = "Funding rate bias"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        if ctx.funding_rate is None:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["Funding rate data not available — skipped"])

        rate = ctx.funding_rate
        if ctx.direction == TradeDirection.LONG:
            favorable = rate < 0.0001
            passed = favorable
            score = 80.0 if favorable else 30.0
        else:
            favorable = rate > -0.0001
            passed = favorable
            score = 80.0 if favorable else 30.0

        reasoning = [f"Funding rate: {rate:.6f} — {'favorable' if favorable else 'unfavorable'} for {ctx.direction.value}"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.05), reasoning=reasoning,
        )


class OpenInterestFilter:
    name = "open_interest"
    description = "Open Interest bias"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        if ctx.open_interest is None:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["Open Interest data not available — skipped"])

        return FilterResult(
            filter_name=self.name, passed=True, score=50.0,
            weight=config.weights.get(self.name, 0.05),
            reasoning=[f"OI data: {ctx.open_interest:.2f}"],
        )


class SessionFilter:
    name = "session"
    description = "Trading session filter"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        if not config.session_allowed:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["Session filter disabled"])

        hour = ctx.candle.timestamp.hour
        weekday = ctx.candle.timestamp.weekday()

        if weekday >= 5:
            return FilterResult(filter_name=self.name, passed=False, score=20.0,
                                reasoning=["Weekend — reduced liquidity"])

        session_name = ""
        session_bonus = 50.0

        if 8 <= hour < 16:
            session_name = "Asia"
        elif 16 <= hour < 21:
            session_name = "London"
            session_bonus = 60.0
        elif 21 <= hour or hour < 3:
            session_name = "New York"
            session_bonus = 65.0 if 21 <= hour < 24 else 55.0
        else:
            session_name = "Asia/London overlap"
            session_bonus = 55.0

        overlap = (13 <= hour < 17) or (21 <= hour < 24)
        if overlap:
            session_bonus = 75.0

        return FilterResult(
            filter_name=self.name, passed=True, score=session_bonus,
            weight=config.weights.get(self.name, 0.04),
            reasoning=[f"Session: {session_name}" + (" (overlap)" if overlap else "")],
        )


class VolatilityFilter:
    name = "volatility"
    description = "ATR-based volatility filter"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        atr_val = _atr(ctx.candles_history, config.atr_period)
        if atr_val is None or atr_val == 0:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["Not enough data for ATR"])

        current_candle_range = ctx.candle.high - ctx.candle.low
        range_ratio = current_candle_range / atr_val if atr_val > 0 else 1.0

        if config.atr_min_mult <= range_ratio <= config.atr_max_mult:
            if config.atr_min_mult * 1.5 <= range_ratio <= config.atr_max_mult * 0.6:
                score = 90.0
                reasoning = [f"ATR range ratio {range_ratio:.2f} — ideal volatility"]
            else:
                score = 65.0
                reasoning = [f"ATR range ratio {range_ratio:.2f} — acceptable volatility"]
            passed = True
        elif range_ratio < config.atr_min_mult:
            score = 20.0
            passed = False
            reasoning = [f"ATR range ratio {range_ratio:.2f} — too low (min {config.atr_min_mult})"]
        else:
            score = 30.0
            passed = False
            reasoning = [f"ATR range ratio {range_ratio:.2f} — too high (max {config.atr_max_mult})"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.07), reasoning=reasoning,
        )


class RiskFilter:
    name = "risk"
    description = "Risk constraint check"

    def evaluate(self, ctx: StrategyContext, config: StrategyConfig) -> FilterResult:
        entry = ctx.entry_price or ctx.candle.close
        stop = ctx.stop_loss

        if stop == 0 or entry == 0:
            return FilterResult(filter_name=self.name, passed=True, score=50.0,
                                data_available=False, reasoning=["No entry/stop defined"])

        risk_distance = abs(entry - stop)
        risk_percent = (risk_distance / entry) * 100

        if risk_percent <= config.max_risk_percent:
            if risk_percent <= config.max_risk_percent * 0.5:
                score = 90.0
                reasoning = [f"Risk {risk_percent:.2f}% — well within limit"]
            else:
                score = 70.0
                reasoning = [f"Risk {risk_percent:.2f}% — acceptable"]
            passed = True
        elif risk_percent <= config.max_risk_percent * 1.5:
            score = 40.0
            passed = False
            reasoning = [f"Risk {risk_percent:.2f}% — exceeds limit ({config.max_risk_percent}%)"]
        else:
            score = 10.0
            passed = False
            reasoning = [f"Risk {risk_percent:.2f}% — far exceeds limit ({config.max_risk_percent}%)"]

        return FilterResult(
            filter_name=self.name, passed=passed, score=round(score, 1),
            weight=config.weights.get(self.name, 0.08), reasoning=reasoning,
        )


ALL_FILTERS: list[Any] = [
    TrendFilter(),
    StructureFilter(),
    SweepFilter(),
    FvgFilter(),
    OrderBlockFilter(),
    VolumeFilter(),
    OrderflowFilter(),
    FundingFilter(),
    OpenInterestFilter(),
    SessionFilter(),
    VolatilityFilter(),
    RiskFilter(),
]
