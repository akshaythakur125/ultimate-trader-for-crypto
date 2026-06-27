from typing import Optional

from ultimate_trader.liquidity_smart_money.models import Candle, FVG


class FairValueGapDetector:
    def __init__(self, min_gap_bps: float = 0.5):
        self.min_gap_bps = min_gap_bps
        self._fvgs: list[FVG] = []

    def analyze(self, candles: list[Candle]) -> list[FVG]:
        new_fvgs: list[FVG] = []
        if len(candles) < 3:
            return new_fvgs

        for i in range(1, len(candles) - 1):
            prev = candles[i - 1]
            curr = candles[i]
            nxt = candles[i + 1]

            if prev.high < nxt.low:
                gap_low = prev.high
                gap_high = nxt.low
                gap_size = ((gap_high - gap_low) / gap_low) * 10000 if gap_low > 0 else 0
                if gap_size >= self.min_gap_bps and not self._already_exists(gap_low, gap_high):
                    fvg = FVG(
                        fvg_type="BULLISH_FVG",
                        gap_high=gap_high,
                        gap_low=gap_low,
                        gap_size=round(gap_size, 2),
                        index=i,
                        description=f"Bullish FVG: {gap_low:.2f} - {gap_high:.2f} ({gap_size:.1f} bps)",
                    )
                    self._fvgs.append(fvg)
                    new_fvgs.append(fvg)

            if prev.low > nxt.high:
                gap_high = prev.low
                gap_low = nxt.high
                gap_size = ((gap_high - gap_low) / gap_low) * 10000 if gap_low > 0 else 0
                if gap_size >= self.min_gap_bps and not self._already_exists(gap_low, gap_high):
                    fvg = FVG(
                        fvg_type="BEARISH_FVG",
                        gap_high=gap_high,
                        gap_low=gap_low,
                        gap_size=round(gap_size, 2),
                        index=i,
                        description=f"Bearish FVG: {gap_low:.2f} - {gap_high:.2f} ({gap_size:.1f} bps)",
                    )
                    self._fvgs.append(fvg)
                    new_fvgs.append(fvg)

        self._update_mitigation(candles)
        return new_fvgs

    def _already_exists(self, gap_low: float, gap_high: float) -> bool:
        for fvg in self._fvgs:
            if abs(fvg.gap_low - gap_low) < 0.01 and abs(fvg.gap_high - gap_high) < 0.01:
                return True
        return False

    def _update_mitigation(self, candles: list[Candle]):
        for fvg in self._fvgs:
            if fvg.is_filled or fvg.is_mitigated:
                continue
            for c in candles:
                if fvg.fvg_type == "BULLISH_FVG":
                    if c.low <= fvg.gap_low and c.high >= fvg.gap_high:
                        fvg.is_filled = True
                    elif c.close <= fvg.gap_high and c.close >= fvg.gap_low:
                        fvg.is_mitigated = True
                elif fvg.fvg_type == "BEARISH_FVG":
                    if c.low <= fvg.gap_low and c.high >= fvg.gap_high:
                        fvg.is_filled = True
                    elif c.close >= fvg.gap_low and c.close <= fvg.gap_high:
                        fvg.is_mitigated = True

    def get_fvgs(self) -> list[FVG]:
        return list(self._fvgs)

    def get_active_fvgs(self) -> list[FVG]:
        return [f for f in self._fvgs if not f.is_filled and not f.is_mitigated]

    def reset(self):
        self._fvgs.clear()
