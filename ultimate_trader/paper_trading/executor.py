import uuid
from datetime import datetime
from typing import Optional

from ultimate_trader.event_bus import EventBus, EventType, get_default_bus, publish_system_event
from ultimate_trader.paper_trading.account import PaperAccount
from ultimate_trader.paper_trading.order import (
    OrderSide,
    OrderStatus,
    OrderType,
    OrderFill,
    PaperOrder,
)
from ultimate_trader.paper_trading.portfolio import ClosedTrade, PaperPosition
from ultimate_trader.signal_engine import FinalRecommendation, SignalReport


class PaperTradeExecutor:
    def __init__(
        self,
        account: Optional[PaperAccount] = None,
        event_bus: Optional[EventBus] = None,
        default_quantity: float = 0.01,
    ):
        self.account = account or PaperAccount()
        self.event_bus = event_bus or get_default_bus()
        self.default_quantity = default_quantity
        self._executed_signals: set[str] = set()

    def evaluate(self, report: SignalReport) -> Optional[PaperOrder]:
        if report.report_id in self._executed_signals:
            return None
        should, reason = self._should_execute(report)
        if not should:
            publish_system_event(
                EventType.SIGNAL_REJECTED,
                "paper_trading.executor",
                {
                    "report_id": report.report_id,
                    "reason": reason,
                    "recommendation": report.final_recommendation.value,
                },
                correlation_id=report.signal_context.context_id if report.signal_context else None,
            )
            return None
        if report.final_recommendation == FinalRecommendation.PAPER_TRADE_CANDIDATE:
            order = self._create_order(report)
            if order:
                self.account.add_order(order)
                self._executed_signals.add(report.report_id)
                publish_system_event(
                    EventType.PAPER_TRADE_CREATED,
                    "paper_trading.executor",
                    {
                        "report_id": report.report_id,
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "quantity": order.quantity,
                        "price": order.price,
                    },
                    correlation_id=report.signal_context.context_id if report.signal_context else None,
                )
                return order
        return None

    def fill_order(
        self,
        order: PaperOrder,
        fill_price: float,
        fill_quantity: Optional[float] = None,
    ) -> Optional[PaperPosition]:
        if order.status != OrderStatus.SUBMITTED:
            return None
        qty = fill_quantity or order.quantity
        fill = OrderFill(
            fill_id=f"FILL-{uuid.uuid4().hex[:8].upper()}",
            price=fill_price,
            quantity=qty,
        )
        order.fills.append(fill)
        order.filled_quantity += qty
        order.average_fill_price = fill_price
        order.status = OrderStatus.FILLED
        order.updated_at = datetime.utcnow()

        position = PaperPosition(
            position_id=f"POS-{uuid.uuid4().hex[:8].upper()}",
            symbol=order.symbol,
            side=order.side,
            entry_price=fill_price,
            quantity=qty,
            entry_fills=[fill],
            correlation_id=order.correlation_id,
        )
        position.current_price = fill_price
        self.account.register_position(position)
        publish_system_event(
            EventType.PAPER_ORDER_FILLED,
            "paper_trading.executor",
            {
                "order_id": order.order_id,
                "position_id": position.position_id,
                "symbol": position.symbol,
                "fill_price": fill_price,
                "quantity": qty,
            },
            correlation_id=order.correlation_id,
        )
        publish_system_event(
            EventType.PAPER_POSITION_OPENED,
            "paper_trading.executor",
            {
                "position_id": position.position_id,
                "symbol": position.symbol,
                "side": position.side.value,
                "entry_price": position.entry_price,
                "quantity": position.quantity,
            },
            correlation_id=order.correlation_id,
        )
        return position

    def close_position(
        self,
        position: PaperPosition,
        exit_price: float,
        exit_reason: str = "manual",
    ) -> Optional[ClosedTrade]:
        if not position.is_open:
            return None
        position.current_price = exit_price
        gross_pnl = position.unrealized_pnl
        fee = abs(gross_pnl) * 0.001
        net_pnl = gross_pnl - fee
        holding_time = (datetime.utcnow() - position.entry_time).total_seconds() / 3600
        risk = abs(position.entry_price - (position.stop_loss or position.entry_price * 0.99))
        rr = abs(gross_pnl) / (risk * position.quantity) if risk > 0 else 0.0
        trade = ClosedTrade(
            trade_id=f"TRADE-{uuid.uuid4().hex[:8].upper()}",
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            fee=fee,
            holding_time_hours=holding_time,
            entry_time=position.entry_time,
            exit_reason=exit_reason,
            rr=rr,
            correlation_id=position.correlation_id,
        )
        self.account.add_closed_trade(trade)
        self.account.remove_position(position.position_id)
        position.quantity = 0.0
        publish_system_event(
            EventType.PAPER_POSITION_CLOSED,
            "paper_trading.executor",
            {
                "position_id": position.position_id,
                "trade_id": trade.trade_id,
                "symbol": trade.symbol,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "exit_reason": exit_reason,
            },
            correlation_id=position.correlation_id,
        )
        return trade

    def _should_execute(self, report: SignalReport) -> tuple[bool, str]:
        if report.final_recommendation == FinalRecommendation.REJECT_SIGNAL:
            return False, "Signal rejected by quality gate"
        if report.final_recommendation == FinalRecommendation.NO_SAFE_ENTRY:
            return False, "No safe entry zone identified"
        if report.final_recommendation == FinalRecommendation.HUMAN_REVIEW:
            return False, "Signal requires human review"
        if report.final_recommendation == FinalRecommendation.WAIT_FOR_ENTRY:
            return False, "Waiting for entry conditions"
        if report.final_recommendation == FinalRecommendation.ALERT_ONLY:
            return False, "Alert only — no execution"
        if report.final_recommendation == FinalRecommendation.PAPER_TRADE_CANDIDATE:
            return True, "Paper trade candidate approved"
        return False, f"Unknown recommendation: {report.final_recommendation}"

    def _create_order(self, report: SignalReport) -> Optional[PaperOrder]:
        tp = report.trade_plan
        if not tp or not tp.entry_zone:
            return None
        ez = tp.entry_zone
        if ez.entry_type.value == "NO_SAFE_ENTRY":
            return None
        side = OrderSide.BUY if ez.direction.value == "LONG" else OrderSide.SELL
        qty = 0.0
        if tp.position_sizing and tp.position_sizing.position_size_units:
            qty = tp.position_sizing.position_size_units
        elif tp.position_sizing:
            risk_amt = self.account.balance * (tp.position_sizing.suggested_risk_percent / 100)
            risk_per_unit = abs(ez.preferred_entry - (tp.stop_plan.stop_loss_price if tp.stop_plan else 0))
            qty = risk_amt / risk_per_unit if risk_per_unit > 0 else self.default_quantity
        else:
            qty = self.default_quantity
        order = PaperOrder(
            order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            symbol=tp.symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=round(qty, 6),
            price=ez.preferred_entry,
            correlation_id=report.signal_context.context_id if report.signal_context else None,
        )
        return order
