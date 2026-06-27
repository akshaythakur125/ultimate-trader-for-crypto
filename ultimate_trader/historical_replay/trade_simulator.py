import uuid
from typing import Optional

from ultimate_trader.historical_replay.models import (
    ExitReason,
    HistoricalCandle,
    ReplayConfig,
    ReplayTrade,
    TradeDirection,
    TradePlan,
)


class TradeSimulator:
    def __init__(self, config: ReplayConfig) -> None:
        self._config = config
        self._active_trades: list[ReplayTrade] = []
        self._completed_trades: list[ReplayTrade] = []

    @property
    def active_trades(self) -> list[ReplayTrade]:
        return list(self._active_trades)

    @property
    def completed_trades(self) -> list[ReplayTrade]:
        return list(self._completed_trades)

    @property
    def all_trades(self) -> list[ReplayTrade]:
        return self._completed_trades + self._active_trades

    def process_candle(self, candle: HistoricalCandle, plans: list[TradePlan]) -> list[ReplayTrade]:
        opened: list[ReplayTrade] = []
        for plan in plans:
            trade = self._try_enter(plan, candle)
            if trade is not None:
                self._active_trades.append(trade)
                opened.append(trade)

        closed: list[ReplayTrade] = []
        still_active: list[ReplayTrade] = []
        for trade in self._active_trades:
            result = self._check_exit(trade, candle)
            if result is not None:
                self._completed_trades.append(result)
                closed.append(result)
            else:
                still_active.append(trade)
        self._active_trades = still_active

        return opened + closed

    def _try_enter(self, plan: TradePlan, candle: HistoricalCandle) -> Optional[ReplayTrade]:
        if plan.symbol != candle.symbol:
            return None
        if plan.entry_zone_low <= candle.high and plan.entry_zone_high >= candle.low:
            if plan.direction == TradeDirection.LONG:
                entry_price = min(candle.high, max(candle.low, (plan.entry_zone_low + plan.entry_zone_high) / 2))
            else:
                entry_price = max(candle.low, min(candle.high, (plan.entry_zone_low + plan.entry_zone_high) / 2))
            return ReplayTrade(
                trade_id=f"RT-{uuid.uuid4().hex[:8].upper()}",
                symbol=plan.symbol,
                direction=plan.direction,
                signal_time=plan.signal_time,
                entry_time=candle.timestamp,
                entry_price=entry_price,
                stop_loss=plan.stop_loss,
                target_price=plan.target_price,
                source_hypothesis=plan.source_hypothesis,
                signal_quality_grade=plan.signal_quality_grade,
            )
        return None

    def _check_exit(self, trade: ReplayTrade, candle: HistoricalCandle) -> Optional[ReplayTrade]:
        exit_reason = None
        exit_price = 0.0
        stop_hit = False
        target_hit = False

        if trade.direction == TradeDirection.LONG:
            if candle.low <= trade.stop_loss:
                stop_hit = True
            if candle.high >= trade.target_price:
                target_hit = True
            if stop_hit and target_hit:
                exit_reason = ExitReason.STOP_LOSS
                exit_price = trade.stop_loss
            elif stop_hit:
                exit_reason = ExitReason.STOP_LOSS
                exit_price = trade.stop_loss
            elif target_hit:
                exit_reason = ExitReason.TAKE_PROFIT
                exit_price = trade.target_price
        else:
            if candle.high >= trade.stop_loss:
                stop_hit = True
            if candle.low <= trade.target_price:
                target_hit = True
            if stop_hit and target_hit:
                exit_reason = ExitReason.STOP_LOSS
                exit_price = trade.stop_loss
            elif stop_hit:
                exit_reason = ExitReason.STOP_LOSS
                exit_price = trade.stop_loss
            elif target_hit:
                exit_reason = ExitReason.TAKE_PROFIT
                exit_price = trade.target_price

        if exit_reason is not None:
            return self._close_trade(trade, candle, exit_reason, exit_price)

        trade.holding_candles += 1

        if trade.holding_candles > 60:
            return self._close_trade(trade, candle, ExitReason.MAX_HOLDING_TIME, candle.close)

        return None

    def _close_trade(
        self,
        trade: ReplayTrade,
        candle: HistoricalCandle,
        exit_reason: ExitReason,
        exit_price: float,
    ) -> ReplayTrade:
        trade.exit_time = candle.timestamp
        trade.exit_price = exit_price
        trade.exit_reason = exit_reason

        if trade.entry_price == 0:
            trade.net_r = 0.0
            return trade

        if trade.direction == TradeDirection.LONG:
            raw_r = (exit_price - trade.entry_price) / abs(trade.entry_price - trade.stop_loss) if trade.stop_loss != trade.entry_price else 0.0
        else:
            raw_r = (trade.entry_price - exit_price) / abs(trade.entry_price - trade.stop_loss) if trade.stop_loss != trade.entry_price else 0.0

        trade.gross_r = raw_r
        stop_range = abs(trade.entry_price - trade.stop_loss) if trade.stop_loss != trade.entry_price else 1.0
        fee_rate = self._config.taker_fee_percent / 100.0
        slip_rate = self._config.slippage_percent / 100.0
        fund_rate = self._config.funding_per_candle_percent / 100.0
        trade.fees_r = fee_rate * 2 * abs(trade.entry_price) / stop_range if trade.stop_loss != trade.entry_price else 0.0
        trade.slippage_r = slip_rate * abs(trade.entry_price) / stop_range if trade.stop_loss != trade.entry_price else 0.0
        trade.funding_r = fund_rate * trade.holding_candles * abs(trade.entry_price) / stop_range if trade.stop_loss != trade.entry_price else 0.0
        trade.net_r = raw_r - trade.fees_r - trade.slippage_r - trade.funding_r

        return trade
