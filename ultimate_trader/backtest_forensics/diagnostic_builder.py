from datetime import datetime
from typing import Any, Optional

from ultimate_trader.backtest_forensics.trade_diagnostics import (
    ExitReason,
    TradeDiagnostics,
    TradeDirection,
)


def build_trade_diagnostics(
    trade: Any,
    entry_price: float = 0.0,
    stop_loss: float = 0.0,
    target_price: float = 0.0,
    entry_time: Optional[datetime] = None,
    exit_time: Optional[datetime] = None,
    candles_history: Optional[list[Any]] = None,
    strategy_candidate: Any = None,
) -> TradeDiagnostics:
    direction = TradeDirection.LONG
    if hasattr(trade, "direction"):
        dir_val = trade.direction
        if isinstance(dir_val, str) and dir_val.upper() == "SHORT":
            direction = TradeDirection.SHORT
        elif hasattr(dir_val, "value") and dir_val.value == "SHORT":
            direction = TradeDirection.SHORT

    ep = entry_price or getattr(trade, "entry_price", 0.0)
    sl = stop_loss or getattr(trade, "stop_loss", 0.0)
    tp = target_price or getattr(trade, "target_price", 0.0)

    net_r = getattr(trade, "net_r", 0.0)
    gross_r = getattr(trade, "gross_r", net_r)
    fees_r = getattr(trade, "fees_r", 0.0)
    slippage_r = getattr(trade, "slippage_r", 0.0)

    exit_reason_str = getattr(trade, "exit_reason", "UNKNOWN")
    if hasattr(exit_reason_str, "value"):
        exit_reason_str = exit_reason_str.value

    holding = getattr(trade, "holding_candles", 0)
    if holding == 0 and hasattr(trade, "entry_time") and hasattr(trade, "exit_time"):
        et = entry_time or trade.entry_time
        xt = exit_time or trade.exit_time
        if et and xt and candles_history:
            holding = len(candles_history)

    entry_to_stop_pct = 0.0
    entry_to_target_pct = 0.0
    if ep > 0 and sl > 0:
        entry_to_stop_pct = abs(ep - sl) / ep * 100
    if ep > 0 and tp > 0:
        entry_to_target_pct = abs(tp - ep) / ep * 100

    rr = 0.0
    if sl > 0 and ep > 0 and tp > 0:
        risk = abs(ep - sl)
        reward = abs(tp - ep)
        rr = reward / risk if risk > 0 else 0.0

    mfe = getattr(trade, "max_favorable_excursion_r", 0.0)
    mae = getattr(trade, "max_adverse_excursion_r", 0.0)

    sig_q = "NONE"
    conf = 0.0
    passed: list[str] = []
    failed: list[str] = []
    if strategy_candidate is not None:
        conf = getattr(strategy_candidate, "total_confidence", 0.0)
        passed = list(getattr(strategy_candidate, "filters_passed", []))
        failed = list(getattr(strategy_candidate, "filters_failed", []))

    return TradeDiagnostics(
        trade_id=getattr(trade, "trade_id", f"TD-{datetime.utcnow().timestamp()}"),
        symbol=getattr(trade, "symbol", "UNKNOWN"),
        direction=direction,
        signal_time=getattr(trade, "signal_time", datetime.utcnow()),
        entry_time=entry_time or getattr(trade, "entry_time", None),
        exit_time=exit_time or getattr(trade, "exit_time", None),
        entry_price=ep,
        stop_loss=sl,
        target_price=tp,
        exit_price=getattr(trade, "exit_price", 0.0),
        exit_reason=ExitReason(exit_reason_str) if exit_reason_str in [e.value for e in ExitReason] else ExitReason.UNKNOWN,
        net_r=net_r,
        gross_r=gross_r,
        fees_r=fees_r,
        slippage_r=slippage_r,
        holding_candles=holding,
        candles_until_exit=getattr(trade, "candles_until_exit", holding),
        max_favorable_excursion_r=mfe,
        max_adverse_excursion_r=mae,
        entry_to_stop_distance_percent=entry_to_stop_pct,
        entry_to_target_distance_percent=entry_to_target_pct,
        rr_ratio=rr,
        signal_quality_grade=sig_q,
        confidence_score=conf,
        filters_passed=passed,
        filters_failed=failed,
    )
