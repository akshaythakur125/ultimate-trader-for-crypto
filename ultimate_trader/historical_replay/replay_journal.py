from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayTrade, TradePlan


class ReplayJournal(BaseModel):
    candles_processed: list[dict] = Field(default_factory=list)
    skipped_signals: list[dict] = Field(default_factory=list)
    generated_plans: list[TradePlan] = Field(default_factory=list)
    executed_trades: list[ReplayTrade] = Field(default_factory=list)
    rejection_reasons: list[dict] = Field(default_factory=list)
    engine_skip_reasons: list[dict] = Field(default_factory=list)

    def add_candle(self, candle: HistoricalCandle) -> None:
        self.candles_processed.append({
            "symbol": candle.symbol,
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        })

    def add_skipped_signal(self, timestamp: str, reason: str) -> None:
        self.skipped_signals.append({"timestamp": timestamp, "reason": reason})

    def add_plan(self, plan: TradePlan) -> None:
        self.generated_plans.append(plan)

    def add_trade(self, trade: ReplayTrade) -> None:
        self.executed_trades.append(trade)

    def add_rejection(self, timestamp: str, reason: str) -> None:
        self.rejection_reasons.append({"timestamp": timestamp, "reason": reason})

    def add_engine_skip(self, engine: str, reason: str) -> None:
        self.engine_skip_reasons.append({"engine": engine, "reason": reason})

    @property
    def total_candles(self) -> int:
        return len(self.candles_processed)

    @property
    def total_plans(self) -> int:
        return len(self.generated_plans)

    @property
    def total_trades(self) -> int:
        return len(self.executed_trades)

    @property
    def total_rejections(self) -> int:
        return len(self.rejection_reasons)

    @property
    def total_engine_skips(self) -> int:
        return len(self.engine_skip_reasons)
