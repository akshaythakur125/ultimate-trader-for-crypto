from typing import Any

from ultimate_trader.backtest_forensics.trade_diagnostics import TradeDiagnostics


class OutcomeStatistics:
    def __init__(self):
        self.total_trades: int = 0
        self.wins: int = 0
        self.losses: int = 0
        self.win_rate: float = 0.0
        self.loss_rate: float = 0.0
        self.avg_r: float = 0.0
        self.avg_mfe_r: float = 0.0
        self.avg_mae_r: float = 0.0
        self.avg_holding_candles: float = 0.0
        self.avg_candles_until_stop: float = 0.0
        self.stopped_within_1_candle: int = 0
        self.stopped_within_1_candle_pct: float = 0.0
        self.stopped_before_0_5r_mfe: int = 0
        self.stopped_before_0_5r_mfe_pct: float = 0.0
        self.reached_1r_mfe_but_stopped: int = 0
        self.reached_1r_mfe_but_stopped_pct: float = 0.0
        self.nearly_hit_target_then_reversed: int = 0
        self.nearly_hit_target_then_reversed_pct: float = 0.0
        self.same_candle_stop_first: int = 0
        self.same_candle_stop_first_pct: float = 0.0


class OutcomeAnalyzer:
    def analyze(self, trades: list[TradeDiagnostics]) -> OutcomeStatistics:
        stats = OutcomeStatistics()
        stats.total_trades = len(trades)

        if not trades:
            return stats

        winners = [t for t in trades if t.is_winner()]
        losers = [t for t in trades if t.is_loser()]
        stats.wins = len(winners)
        stats.losses = len(losers)
        stats.win_rate = (stats.wins / stats.total_trades) * 100 if stats.total_trades > 0 else 0.0
        stats.loss_rate = (stats.losses / stats.total_trades) * 100 if stats.total_trades > 0 else 0.0
        stats.avg_r = sum(t.net_r for t in trades) / stats.total_trades
        stats.avg_mfe_r = sum(t.max_favorable_excursion_r for t in trades) / stats.total_trades
        stats.avg_mae_r = sum(t.max_adverse_excursion_r for t in trades) / stats.total_trades
        stats.avg_holding_candles = sum(t.holding_candles for t in trades) / stats.total_trades

        stopped = [t for t in trades if t.exit_reason.value == "STOP_LOSS"]
        stats.avg_candles_until_stop = sum(t.candles_until_exit for t in stopped) / len(stopped) if stopped else 0.0

        stats.stopped_within_1_candle = sum(1 for t in trades if t.exit_reason.value == "STOP_LOSS" and t.holding_candles <= 1)
        stats.stopped_within_1_candle_pct = (stats.stopped_within_1_candle / stats.total_trades) * 100

        stats.stopped_before_0_5r_mfe = sum(
            1 for t in trades if t.exit_reason.value == "STOP_LOSS" and t.max_favorable_excursion_r < 0.5
        )
        stats.stopped_before_0_5r_mfe_pct = (stats.stopped_before_0_5r_mfe / stats.total_trades) * 100

        stats.reached_1r_mfe_but_stopped = sum(
            1 for t in trades if t.exit_reason.value == "STOP_LOSS" and t.max_favorable_excursion_r >= 1.0 and t.net_r <= 0
        )
        stats.reached_1r_mfe_but_stopped_pct = (stats.reached_1r_mfe_but_stopped / stats.total_trades) * 100

        stats.nearly_hit_target_then_reversed = sum(
            1 for t in trades
            if t.exit_reason.value == "STOP_LOSS" and t.target_price > 0
            and (t.rr_ratio > 0 and t.max_favorable_excursion_r >= t.rr_ratio * 0.8)
        )
        stats.nearly_hit_target_then_reversed_pct = (stats.nearly_hit_target_then_reversed / stats.total_trades) * 100

        stats.same_candle_stop_first = sum(
            1 for t in trades if t.exit_reason.value == "STOP_LOSS" and t.holding_candles == 1
        )
        stats.same_candle_stop_first_pct = (stats.same_candle_stop_first / stats.total_trades) * 100

        return stats
