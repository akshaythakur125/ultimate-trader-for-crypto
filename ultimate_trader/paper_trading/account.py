from datetime import datetime
from decimal import Decimal
from typing import Optional

from ultimate_trader.paper_trading.order import PaperOrder
from ultimate_trader.paper_trading.portfolio import ClosedTrade, PaperPosition


class PaperAccount:
    def __init__(
        self,
        starting_balance: float = 100_000.0,
        currency: str = "USDT",
        max_leverage: int = 1,
    ):
        self.starting_balance = Decimal(str(starting_balance))
        self.currency = currency
        self.max_leverage = max_leverage
        self._realized_pnl = Decimal("0")
        self._orders: list[PaperOrder] = []
        self._positions: dict[str, PaperPosition] = {}
        self._closed_trades: list[ClosedTrade] = []
        self.created_at = datetime.utcnow()

    @property
    def balance(self) -> float:
        return float(self.starting_balance + self._realized_pnl)

    @property
    def realized_pnl(self) -> float:
        return float(self._realized_pnl)

    @property
    def total_pnl(self) -> float:
        return float(self._realized_pnl)

    @property
    def total_pnl_percent(self) -> float:
        if self.starting_balance == 0:
            return 0.0
        return float((self._realized_pnl / self.starting_balance) * 100)

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self._positions.values())

    @property
    def equity(self) -> float:
        return self.balance + self.unrealized_pnl

    @property
    def used_margin(self) -> float:
        return sum(p.margin for p in self._positions.values())

    @property
    def free_balance(self) -> float:
        return self.balance - self.used_margin

    @property
    def positions(self) -> dict[str, PaperPosition]:
        return dict(self._positions)

    @property
    def open_positions(self) -> dict[str, PaperPosition]:
        return {k: v for k, v in self._positions.items() if v.is_open}

    @property
    def orders(self) -> list[PaperOrder]:
        return list(self._orders)

    @property
    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed_trades)

    def add_order(self, order: PaperOrder):
        self._orders.append(order)

    def register_position(self, position: PaperPosition):
        self._positions[position.position_id] = position

    def get_position(self, position_id: str) -> Optional[PaperPosition]:
        return self._positions.get(position_id)

    def remove_position(self, position_id: str) -> bool:
        if position_id in self._positions:
            del self._positions[position_id]
            return True
        return False

    def add_closed_trade(self, trade: ClosedTrade):
        self._closed_trades.append(trade)
        self._realized_pnl += Decimal(str(trade.net_pnl))

    def update_position_price(self, position_id: str, current_price: float):
        pos = self._positions.get(position_id)
        if pos:
            pos.current_price = current_price

    def has_funds_for(self, required_margin: float) -> bool:
        return self.free_balance >= required_margin

    def reset(self):
        self._realized_pnl = Decimal("0")
        self._orders.clear()
        self._positions.clear()
        self._closed_trades.clear()

    def summary(self) -> dict:
        return {
            "starting_balance": float(self.starting_balance),
            "current_balance": self.balance,
            "equity": self.equity,
            "total_pnl": self.total_pnl,
            "total_pnl_percent": self.total_pnl_percent,
            "unrealized_pnl": self.unrealized_pnl,
            "used_margin": self.used_margin,
            "free_balance": self.free_balance,
            "open_positions": len(self._positions),
            "closed_trades": len(self._closed_trades),
            "total_orders": len(self._orders),
            "currency": self.currency,
        }
