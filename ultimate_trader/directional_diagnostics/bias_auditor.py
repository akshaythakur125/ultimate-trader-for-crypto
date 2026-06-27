from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class TradeOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"


class DirectionalBiasAudit(BaseModel):
    trade_id: str
    symbol: str
    signal_time: datetime
    direction_taken: str
    outcome: TradeOutcome
    net_r: float = 0.0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    opposite_would_have_won: bool = False
    original_direction_source: str = "unknown"
    lsm_bias: str = ""
    microstructure_bias: str = ""
    orderflow_bias: str = ""
    strategy_bias: str = ""
    confluence_score: float = 0.0
    confidence_score: float = 0.0
    failure_classification: str = ""


class BiasAuditSummary:
    def __init__(self):
        self.total_trades: int = 0
        self.long_trades: int = 0
        self.short_trades: int = 0
        self.long_win_rate: float = 0.0
        self.short_win_rate: float = 0.0
        self.long_expectancy: float = 0.0
        self.short_expectancy: float = 0.0
        self.wrong_direction_count: int = 0
        self.wrong_direction_rate: float = 0.0
        self.direction_accuracy: float = 0.0
        self.long_edge_status: str = "NO_EDGE"
        self.short_edge_status: str = "NO_EDGE"
        self.suspected_bias_failure: bool = False
        self.audit_summary: str = ""


class BiasAuditor:
    def __init__(self):
        self._audits: list[DirectionalBiasAudit] = []

    def audit_trade(
        self,
        trade_id: str,
        symbol: str,
        signal_time: datetime,
        direction_taken: str,
        net_r: float,
        mfe_r: float = 0.0,
        mae_r: float = 0.0,
        lsm_bias: str = "",
        microstructure_bias: str = "",
        orderflow_bias: str = "",
        strategy_bias: str = "",
        confluence_score: float = 0.0,
        confidence_score: float = 0.0,
        failure_classification: str = "",
    ) -> DirectionalBiasAudit:
        outcome = TradeOutcome.WIN if net_r > 0 else TradeOutcome.LOSS
        opposite_would_have_won = False
        if outcome == TradeOutcome.LOSS and mae_r > 0 and mfe_r > 0:
            if direction_taken.upper() == "LONG":
                if mae_r > abs(net_r) * 0.7:
                    opposite_would_have_won = True
            else:
                if mae_r > abs(net_r) * 0.7:
                    opposite_would_have_won = True

        audit = DirectionalBiasAudit(
            trade_id=trade_id,
            symbol=symbol,
            signal_time=signal_time,
            direction_taken=direction_taken.upper(),
            outcome=outcome,
            net_r=net_r,
            mfe_r=mfe_r,
            mae_r=mae_r,
            opposite_would_have_won=opposite_would_have_won,
            original_direction_source=lsm_bias or "unknown",
            lsm_bias=lsm_bias,
            microstructure_bias=microstructure_bias,
            orderflow_bias=orderflow_bias,
            strategy_bias=strategy_bias,
            confluence_score=confluence_score,
            confidence_score=confidence_score,
            failure_classification=failure_classification,
        )
        self._audits.append(audit)
        return audit

    def audit_trade_diagnostics(self, td: TradeDiagnostics) -> DirectionalBiasAudit:
        comps = td.directional_components
        return self.audit_trade(
            trade_id=td.trade_id,
            symbol=td.symbol,
            signal_time=td.signal_time,
            direction_taken=td.direction.value,
            net_r=td.net_r,
            mfe_r=td.max_favorable_excursion_r,
            mae_r=td.max_adverse_excursion_r,
            lsm_bias="LONG" if comps.get("sweep_bias", 0) > 0 else "SHORT" if comps.get("sweep_bias", 0) < 0 else "NEUTRAL",
            microstructure_bias="BULLISH" if comps.get("microstructure_bias", 0) > 0 else "BEARISH" if comps.get("microstructure_bias", 0) < 0 else "NEUTRAL",
            orderflow_bias="LONG" if comps.get("orderflow_bias", 0) > 0 else "SHORT" if comps.get("orderflow_bias", 0) < 0 else "NEUTRAL",
            strategy_bias=td.directional_vote,
            confluence_score=comps.get("confluence_score", 0.0),
            confidence_score=td.confidence_score,
        )

    def summarize(self) -> BiasAuditSummary:
        summary = BiasAuditSummary()
        summary.total_trades = len(self._audits)
        if not self._audits:
            return summary

        longs = [a for a in self._audits if a.direction_taken == "LONG"]
        shorts = [a for a in self._audits if a.direction_taken == "SHORT"]
        summary.long_trades = len(longs)
        summary.short_trades = len(shorts)
        summary.wrong_direction_count = sum(1 for a in self._audits if a.opposite_would_have_won)

        if longs:
            long_wins = sum(1 for a in longs if a.outcome == TradeOutcome.WIN)
            summary.long_win_rate = long_wins / len(longs)
            summary.long_expectancy = sum(a.net_r for a in longs) / len(longs)
            if summary.long_win_rate > 0.5 and summary.long_expectancy > 0:
                summary.long_edge_status = "POSITIVE_EDGE"
            elif summary.long_win_rate > 0.4:
                summary.long_edge_status = "WEAK_EDGE"
            else:
                summary.long_edge_status = "NO_EDGE"

        if shorts:
            short_wins = sum(1 for a in shorts if a.outcome == TradeOutcome.WIN)
            summary.short_win_rate = short_wins / len(shorts)
            summary.short_expectancy = sum(a.net_r for a in shorts) / len(shorts)
            if summary.short_win_rate > 0.5 and summary.short_expectancy > 0:
                summary.short_edge_status = "POSITIVE_EDGE"
            elif summary.short_win_rate > 0.4:
                summary.short_edge_status = "WEAK_EDGE"
            else:
                summary.short_edge_status = "NO_EDGE"

        correct_dir = sum(1 for a in self._audits if (a.outcome == TradeOutcome.WIN) or a.opposite_would_have_won)
        summary.direction_accuracy = correct_dir / summary.total_trades if summary.total_trades > 0 else 0.0
        summary.wrong_direction_rate = summary.wrong_direction_count / summary.total_trades if summary.total_trades > 0 else 0.0

        if summary.wrong_direction_rate > 0.5:
            summary.suspected_bias_failure = True

        parts = []
        if summary.long_trades > 0:
            parts.append(f"Long: {summary.long_trades}t, WR={summary.long_win_rate*100:.1f}%, EV={summary.long_expectancy:.2f}R ({summary.long_edge_status})")
        if summary.short_trades > 0:
            parts.append(f"Short: {summary.short_trades}t, WR={summary.short_win_rate*100:.1f}%, EV={summary.short_expectancy:.2f}R ({summary.short_edge_status})")
        parts.append(f"Direction accuracy: {summary.direction_accuracy*100:.1f}%")
        parts.append(f"Wrong-direction rate: {summary.wrong_direction_rate*100:.1f}%")
        if summary.suspected_bias_failure:
            parts.append("BIAS FAILURE SUSPECTED — high wrong-direction rate")
        summary.audit_summary = " | ".join(parts)
        return summary
