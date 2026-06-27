from datetime import timedelta
from typing import Optional

from ultimate_trader.orderflow_intelligence.models import (
    AggressorSide,
    FlowWindow,
    TradePrint,
    TradeSide,
)


class TradeFlowBuffer:
    def __init__(self, window_seconds: int = 60, max_trades: int = 10000):
        self.window_seconds = window_seconds
        self.max_trades = max_trades
        self._trades: list[TradePrint] = []

    def add_trade(self, trade: TradePrint):
        self._trades.append(trade)
        if len(self._trades) > self.max_trades:
            self._trades.pop(0)

    def get_window(self, symbol: str) -> FlowWindow:
        now = __import__("datetime").datetime.utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)
        recent = [t for t in self._trades if t.symbol == symbol and t.timestamp >= cutoff]

        if not recent:
            return FlowWindow(symbol=symbol)

        buy_vol = sum(t.quantity for t in recent if t.aggressor_side == AggressorSide.BUYER)
        sell_vol = sum(t.quantity for t in recent if t.aggressor_side == AggressorSide.SELLER)
        large_trades = [t for t in recent if t.quantity >= 1.0]
        total_val = sum(t.trade_value for t in recent)
        avg_size = total_val / len(recent) if recent else 0.0
        cumulative = sum(
            t.quantity if t.aggressor_side == AggressorSide.BUYER else -t.quantity
            for t in recent
        )

        return FlowWindow(
            symbol=symbol,
            timeframe_seconds=self.window_seconds,
            start_time=min(t.timestamp for t in recent),
            end_time=max(t.timestamp for t in recent),
            trades=recent,
            total_buy_volume=buy_vol,
            total_sell_volume=sell_vol,
            buy_sell_delta=buy_vol - sell_vol,
            cumulative_delta=cumulative,
            total_trade_value=total_val,
            average_trade_size=avg_size,
            large_trade_count=len(large_trades),
            trade_count=len(recent),
        )

    def reset(self):
        self._trades.clear()
