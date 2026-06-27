from pydantic import BaseModel, Field

from ultimate_trader.microstructure_engine.models import ImbalanceBias, OrderBookSnapshot


class ImbalanceResult(BaseModel):
    imbalance_score: float = 0.0
    bias: ImbalanceBias = ImbalanceBias.NEUTRAL
    imbalance_reason: str = ""


class OrderBookImbalanceAnalyzer:
    def __init__(
        self,
        depth_levels: int = 10,
        bias_threshold: float = 0.3,
        strong_bias_threshold: float = 0.35,
    ):
        self.depth_levels = depth_levels
        self.bias_threshold = bias_threshold
        self.strong_bias_threshold = strong_bias_threshold  # bid_ratio > 0.5 + this = strong

    def analyze(self, snapshot: OrderBookSnapshot) -> ImbalanceResult:
        top_bids = snapshot.bids[:self.depth_levels]
        top_asks = snapshot.asks[:self.depth_levels]

        bid_volume = sum(b.quantity for b in top_bids)
        ask_volume = sum(a.quantity for a in top_asks)
        total_volume = bid_volume + ask_volume

        if total_volume == 0:
            return ImbalanceResult(
                imbalance_score=50.0,
                bias=ImbalanceBias.NEUTRAL,
                imbalance_reason="No order book data available",
            )

        bid_ratio = bid_volume / total_volume
        imbalance_score = bid_ratio * 100

        bias = self._determine_bias(bid_ratio)
        reason = self._build_reason(bias, bid_ratio, bid_volume, ask_volume, imbalance_score)

        return ImbalanceResult(
            imbalance_score=round(imbalance_score, 2),
            bias=bias,
            imbalance_reason=reason,
        )

    def _determine_bias(self, bid_ratio: float) -> ImbalanceBias:
        if bid_ratio > 0.5 + self.bias_threshold:
            return ImbalanceBias.LONG
        if bid_ratio < 0.5 - self.bias_threshold:
            return ImbalanceBias.SHORT
        return ImbalanceBias.NEUTRAL

    def _build_reason(
        self,
        bias: ImbalanceBias,
        bid_ratio: float,
        bid_vol: float,
        ask_vol: float,
        score: float,
    ) -> str:
        if bias == ImbalanceBias.LONG:
            strength = "strong" if bid_ratio > 0.5 + self.strong_bias_threshold else "moderate"
            return (
                f"{strength} bid dominance: {bid_vol:.1f} vs {ask_vol:.1f} "
                f"(score={score:.0f}/100)"
            )
        if bias == ImbalanceBias.SHORT:
            strength = "strong" if bid_ratio < 0.5 - self.strong_bias_threshold else "moderate"
            return (
                f"{strength} ask dominance: {ask_vol:.1f} vs {bid_vol:.1f} "
                f"(score={score:.0f}/100)"
            )
        return (
            f"balanced book: {bid_vol:.1f} bid vs {ask_vol:.1f} ask "
            f"(score={score:.0f}/100)"
        )
