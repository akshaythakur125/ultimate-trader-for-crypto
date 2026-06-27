from typing import Optional

from ultimate_trader.liquidity_smart_money.models import Candle, FVG, OrderBlock


class OrderBlockDetector:
    def __init__(self, lookback: int = 10, max_blocks: int = 100):
        self.lookback = lookback
        self.max_blocks = max_blocks
        self._blocks: list[OrderBlock] = []

    def analyze(self, candles: list[Candle], fvgs: list[FVG]) -> list[OrderBlock]:
        new_blocks: list[OrderBlock] = []
        if len(candles) < 3:
            return new_blocks

        for fvg in fvgs:
            if fvg.index < 1 or fvg.index >= len(candles):
                continue
            ob_candle = candles[fvg.index - 1]
            if self._block_exists(ob_candle.high, ob_candle.low):
                continue

            if fvg.fvg_type == "BULLISH_FVG":
                ob = OrderBlock(
                    ob_type="BULLISH_OB",
                    price_high=ob_candle.high,
                    price_low=ob_candle.low,
                    index=fvg.index - 1,
                    strength_score=self._compute_strength(ob_candle, candles, "bullish"),
                    description=f"Bullish OB: {ob_candle.low:.2f} - {ob_candle.high:.2f}",
                )
                self._blocks.append(ob)
                new_blocks.append(ob)

            elif fvg.fvg_type == "BEARISH_FVG":
                ob = OrderBlock(
                    ob_type="BEARISH_OB",
                    price_high=ob_candle.high,
                    price_low=ob_candle.low,
                    index=fvg.index - 1,
                    strength_score=self._compute_strength(ob_candle, candles, "bearish"),
                    description=f"Bearish OB: {ob_candle.low:.2f} - {ob_candle.high:.2f}",
                )
                self._blocks.append(ob)
                new_blocks.append(ob)

        self._update_mitigation(candles)
        self._detect_breaker_blocks(candles, new_blocks)
        if len(self._blocks) > self.max_blocks:
            self._blocks[:] = self._blocks[-self.max_blocks:]
        return new_blocks

    def _block_exists(self, high: float, low: float) -> bool:
        for b in self._blocks:
            if abs(b.price_high - high) < 0.01 and abs(b.price_low - low) < 0.01:
                return True
        return False

    def _compute_strength(self, ob_candle: Candle, candles: list[Candle], direction: str) -> float:
        score = 30.0
        body = abs(ob_candle.close - ob_candle.open)
        total_range = ob_candle.high - ob_candle.low
        if total_range > 0:
            body_ratio = body / total_range
            if body_ratio > 0.7:
                score += 25
            elif body_ratio > 0.5:
                score += 15
            else:
                score += 5
        if ob_candle.volume > 0:
            avg_vol = sum(c.volume for c in candles[-10:]) / max(len(candles[-10:]), 1)
            if avg_vol > 0 and ob_candle.volume > avg_vol * 1.5:
                score += 20
            elif avg_vol > 0 and ob_candle.volume > avg_vol * 1.2:
                score += 10
        if direction == "bullish" and ob_candle.close < ob_candle.open:
            score += 15
        elif direction == "bearish" and ob_candle.close > ob_candle.open:
            score += 15
        body_dir = abs(ob_candle.close - ob_candle.open)
        if direction == "bullish":
            score += min(body_dir / max(ob_candle.low, 0.01) * 100, 10)
        else:
            score += min(body_dir / max(ob_candle.high, 0.01) * 100, 10)
        return round(min(score, 100), 2)

    def _update_mitigation(self, candles: list[Candle]):
        for block in self._blocks:
            if block.is_invalidated or block.is_mitigated:
                continue
            for c in candles:
                if block.ob_type in ("BULLISH_OB", "MITIGATION_BLOCK"):
                    if c.low <= block.price_low:
                        block.is_mitigated = True
                        break
                elif block.ob_type in ("BEARISH_OB", "BREAKER_BLOCK"):
                    if c.high >= block.price_high:
                        block.is_mitigated = True
                        break

    def _detect_breaker_blocks(self, candles: list[Candle], new_blocks: Optional[list[OrderBlock]] = None):
        if not new_blocks:
            return
        for block in new_blocks:
            if block.ob_type == "BULLISH_OB" and block.is_mitigated:
                for c in candles:
                    if c.high > block.price_high:
                        bb = OrderBlock(
                            ob_type="BREAKER_BLOCK",
                            price_high=block.price_high,
                            price_low=block.price_low,
                            is_mitigated=False,
                            strength_score=block.strength_score * 0.8,
                            index=block.index,
                            description=f"Breaker block from mitigated bullish OB: {block.price_low:.2f} - {block.price_high:.2f}",
                        )
                        self._blocks.append(bb)
                        break
            elif block.ob_type == "BEARISH_OB" and block.is_mitigated:
                for c in candles:
                    if c.low < block.price_low:
                        bb = OrderBlock(
                            ob_type="BREAKER_BLOCK",
                            price_high=block.price_high,
                            price_low=block.price_low,
                            is_mitigated=False,
                            strength_score=block.strength_score * 0.8,
                            index=block.index,
                            description=f"Breaker block from mitigated bearish OB: {block.price_low:.2f} - {block.price_high:.2f}",
                        )
                        self._blocks.append(bb)
                        break

    def get_blocks(self) -> list[OrderBlock]:
        return list(self._blocks)

    def get_active_blocks(self) -> list[OrderBlock]:
        return [b for b in self._blocks if not b.is_mitigated and not b.is_invalidated]

    def reset(self):
        self._blocks.clear()
