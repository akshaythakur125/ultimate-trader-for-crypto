import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.historical_replay.candle_replayer import CandleReplayer
from ultimate_trader.historical_replay.data_loader import HistoricalDataLoader
from ultimate_trader.historical_replay.metrics import ReplayMetrics
from ultimate_trader.historical_replay.models import (
    ReplayConfig,
    TradeDirection,
)
from ultimate_trader.historical_replay.replay_report import ReplayReport
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator
from ultimate_trader.historical_replay.replay_journal import ReplayJournal
from ultimate_trader.historical_replay.pipeline_runner import ReplayPipelineRunner
from ultimate_trader.liquidity_smart_money import (
    SwingDetector,
    LiquidityPoolDetector,
    SweepDetector,
    MarketStructureEngine,
    FairValueGapDetector,
    OrderBlockDetector,
    PremiumDiscountEngine,
    DisplacementEngine,
    ConfluenceEngine,
    Candle,
)


CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "historical", "BTCUSDT_15m.csv")


def build_lsm_engines(config: ReplayConfig):
    class LSMContainer:
        def __init__(self):
            self.swing = SwingDetector(lookback=5)
            self.pools = LiquidityPoolDetector()
            self.sweep = SweepDetector()
            self.structure = MarketStructureEngine(lookback=5)
            self.fvg = FairValueGapDetector(min_gap_bps=0.5)
            self.ob = OrderBlockDetector()
            self.pd = PremiumDiscountEngine()
            self.disp = DisplacementEngine()
            self.conf = ConfluenceEngine()

        def get(self, name):
            return {
                "swing_detector": self.swing,
                "liquidity_pool_detector": self.pools,
                "sweep_detector": self.sweep,
                "market_structure_engine": self.structure,
                "fair_value_gap_detector": self.fvg,
                "order_block_detector": self.ob,
                "premium_discount_engine": self.pd,
                "displacement_engine": self.disp,
                "confluence_engine": self.conf,
            }.get(name)

    return LSMContainer()


def main():
    print("=" * 60)
    print("Ultimate Trader -- Historical Replay Engine")
    print("=" * 60)

    csv_path = os.path.abspath(CSV_PATH)
    if not os.path.exists(csv_path):
        print(f"Error: CSV not found at {csv_path}")
        print("Run scripts/download_bingx_ohlcv.py first.")
        sys.exit(1)

    print(f"\nLoading data from: {csv_path}")
    loader = HistoricalDataLoader()
    try:
        candles = loader.load_csv(csv_path)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        sys.exit(1)

    print(f"Candles loaded: {len(candles)}")
    print(f"Date range: {candles[0].timestamp.strftime('%Y-%m-%d %H:%M')} -> {candles[-1].timestamp.strftime('%Y-%m-%d %H:%M')}")
    print(f"Symbol: {candles[0].symbol}, Timeframe: {candles[0].timeframe}")

    config = ReplayConfig(
        confluence_score_threshold=30.0,
        min_rr=3.0,
        warmup_candles=50,
        taker_fee_percent=0.04,
        slippage_percent=0.02,
        funding_per_candle_percent=0.001,
        stop_distance_multiplier=1.5,
        target_rr=3.0,
    )

    journal = ReplayJournal()
    lsm = build_lsm_engines(config)
    runner = ReplayPipelineRunner(config, journal, liquidity_smart_money=lsm)
    sim = TradeSimulator(config)
    replayer = CandleReplayer(candles, warmup=config.warmup_candles)

    print(f"\nRunning replay ({config.warmup_candles} warmup candles)...")
    print("-" * 60)

    warmup_offset = config.warmup_candles
    while True:
        candle = replayer.step()
        if candle is None:
            break

        idx = replayer.current_index
        journal.add_candle(candle)

        if idx < warmup_offset:
            continue

        plan = runner.run_candle(candle, idx)
        plans_to_process = []
        if plan is not None:
            plans_to_process = [plan]
            existing_plans = [p for p in runner.pending_plans if p.plan_id != plan.plan_id]
            runner._pending_plans = existing_plans

        candle_lsm = Candle(
            symbol=candle.symbol, timeframe=candle.timeframe,
            timestamp=candle.timestamp, open=candle.open,
            high=candle.high, low=candle.low, close=candle.close,
            volume=candle.volume,
        )
        sim.process_candle(candle_lsm, plans_to_process)

    candles_processed = replayer.current_index + 1
    total_signals = journal.total_plans + journal.total_rejections
    metrics = ReplayMetrics.calculate(
        sim.completed_trades,
        total_signals,
        journal.total_rejections,
    )

    report = ReplayReport.build(
        report_id=f"RR-{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        symbol=candles[0].symbol,
        timeframe=candles[0].timeframe,
        start_time=candles[0].timestamp,
        end_time=candles[-1].timestamp,
        candles_processed=candles_processed,
        metrics=metrics,
        trades=sim.completed_trades,
        rejected_summary=journal.rejection_reasons,
        engine_skip_summary=journal.engine_skip_reasons,
    )

    print("\n" + "=" * 60)
    print("REPLAY RESULTS")
    print("=" * 60)
    print(f"  Candles processed:  {candles_processed}")
    print(f"  Signals generated:  {total_signals}")
    print(f"  Signals rejected:   {journal.total_rejections}")
    print(f"  Trades executed:    {metrics.executed_trades}")
    print(f"  Win rate:           {metrics.win_rate:.1%}")
    print(f"  Expectancy (R):     {metrics.expectancy_r:.2f}")
    print(f"  Profit factor:      {metrics.profit_factor:.2f}")
    print(f"  Max drawdown (R):   {metrics.max_drawdown_r:.2f}")
    print(f"  Avg holding (candles): {metrics.average_holding_time:.1f}")
    print(f"  Best trade (R):     {metrics.best_trade_r:.2f}")
    print(f"  Worst trade (R):    {metrics.worst_trade_r:.2f}")
    print(f"  Max consecutive L:  {metrics.max_consecutive_losses}")
    print(f"  Conversion rate:    {metrics.signal_to_trade_conversion_rate:.1%}")
    print(f"  Engine skips:       {journal.total_engine_skips}")
    print("-" * 60)
    print(f"  Final conclusion:   {report.final_conclusion.value}")
    print(f"  Explanation:        {report.explanation}")
    print("=" * 60)


if __name__ == "__main__":
    main()
