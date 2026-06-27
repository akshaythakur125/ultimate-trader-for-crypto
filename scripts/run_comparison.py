import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.historical_replay.data_loader import HistoricalDataLoader
from ultimate_trader.historical_replay.models import ReplayConfig, TradeDirection, TradePlan
from ultimate_trader.liquidity_smart_money.confluence_engine import ConfluenceEngine
from ultimate_trader.liquidity_smart_money.displacement import DisplacementEngine
from ultimate_trader.liquidity_smart_money.fair_value_gap import FairValueGapDetector
from ultimate_trader.liquidity_smart_money.liquidity_pools import LiquidityPoolDetector
from ultimate_trader.liquidity_smart_money.market_structure import MarketStructureEngine
from ultimate_trader.liquidity_smart_money.models import Candle as LsmCandle
from ultimate_trader.liquidity_smart_money.order_block import OrderBlockDetector
from ultimate_trader.liquidity_smart_money.premium_discount import PremiumDiscountEngine
from ultimate_trader.liquidity_smart_money.sweep_detector import SweepDetector
from ultimate_trader.liquidity_smart_money.swing_detector import SwingDetector
from ultimate_trader.strategy_engine import StrategyConfig, run_comparison

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "historical", "BTCUSDT_15m.csv")


def build_lsm_provider():
    swing = SwingDetector(lookback=5)
    pools = LiquidityPoolDetector()
    sweep = SweepDetector()
    structure = MarketStructureEngine(lookback=5)
    fvg = FairValueGapDetector(min_gap_bps=0.5)
    ob = OrderBlockDetector()
    pd = PremiumDiscountEngine()
    disp = DisplacementEngine()
    conf = ConfluenceEngine()
    candles_lsm: list[LsmCandle] = []

    def provider(candle, idx):
        lc = LsmCandle(
            symbol=candle.symbol, timeframe=candle.timeframe,
            timestamp=candle.timestamp, open=candle.open,
            high=candle.high, low=candle.low, close=candle.close,
            volume=candle.volume,
        )
        candles_lsm.append(lc)
        swing.add_candle(lc)

        swing_highs = swing.get_swing_highs()
        swing_lows = swing.get_swing_lows()
        equal_highs = swing.get_equal_highs()
        equal_lows = swing.get_equal_lows()

        zones = pools.analyze(swing_highs, swing_lows, equal_highs, equal_lows, candle.close, [])
        sweeps_out = sweep.analyze(candles_lsm[-5:], zones)
        struct_events = structure.analyze(swing_highs, swing_lows, candles_lsm[-10:])
        fvgs_out = fvg.analyze(candles_lsm[-5:])
        obs = ob.analyze(candles_lsm[-5:], fvgs_out)
        pd_state = pd.analyze(swing_highs, swing_lows, candle.close)
        disp_result = disp.analyze(candles_lsm[-5:])
        conf_result = conf.analyze(
            zones, sweeps_out, struct_events, fvgs_out, obs, pd_state,
            [disp_result] if disp_result else [],
        )

        direction = "LONG"
        if conf_result.directional_bias.value in ("SHORT", "SHORT"):
            direction = "SHORT"

        return {
            "direction": direction,
            "confluence_score": conf_result.confluence_score,
            "trade_permission": conf_result.trade_permission,
            "sweeps": sweeps_out,
            "structure_events": struct_events,
            "fvgs": fvgs_out,
            "order_blocks": obs,
            "risk_score": 0.0,
        }

    return provider


def main():
    print("=" * 70)
    print("Ultimate Trader -- Strategy Engine Comparison")
    print("=" * 70)

    csv_path = os.path.abspath(CSV_PATH)
    if not os.path.exists(csv_path):
        print(f"Error: CSV not found at {csv_path}")
        print("Run scripts/download_bingx_ohlcv.py first.")
        sys.exit(1)

    print(f"\nLoading data from: {csv_path}")
    loader = HistoricalDataLoader()
    candles = loader.load_csv(csv_path)
    print(f"Candles loaded: {len(candles)}")
    print(f"Date range: {candles[0].timestamp} -> {candles[-1].timestamp}")

    config = StrategyConfig(
        confidence_threshold=60.0,
        ema_periods=[20, 50, 100, 200],
        atr_period=14,
        volume_lookback=20,
        min_volume_ratio=0.8,
        max_risk_percent=2.0,
        session_allowed=True,
    )

    rcfg = ReplayConfig(
        confluence_score_threshold=30.0,
        min_rr=3.0,
        warmup_candles=50,
        taker_fee_percent=0.04,
        slippage_percent=0.02,
        funding_per_candle_percent=0.001,
    )

    lsm_provider = build_lsm_provider()

    print("\nRunning comparison...")
    print("-" * 70)
    result = run_comparison(
        candles=candles,
        lsm_data_provider=lsm_provider,
        config=config,
        old_replay_config=rcfg,
        new_replay_config=rcfg,
    )

    print("\nCOMPARISON RESULTS")
    print("=" * 70)
    print(f"  {'Metric':<25} {'LSM Only':>10} {'Strategy':>10} {'Change':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10}")
    print(f"  {'Trades':<25} {result.old_trades:>10} {result.new_trades:>10} {result.new_trades - result.old_trades:>+10}")
    print(f"  {'Win Rate':<25} {result.old_win_rate:>9.1f}% {result.new_win_rate:>9.1f}% {result.win_rate_change:>+9.1f}%")
    print(f"  {'Expectancy (R)':<25} {result.old_expectancy:>10.2f} {result.new_expectancy:>10.2f} {result.expectancy_change:>+10.2f}")
    print(f"  {'Profit Factor':<25} {result.old_profit_factor:>10.2f} {result.new_profit_factor:>10.2f} {result.profit_factor_change:>+9.1f}%")
    print(f"  {'Max DD (%)':<25} {result.old_max_drawdown:>10.2f} {result.new_max_drawdown:>10.2f} {result.drawdown_change:>+10.2f}")
    print(f"  {'Max DD (R)':<25} {'N/A':>10} {'N/A':>10} {'N/A':>10}")
    print("-" * 70)
    print(f"  Improvement: {result.improvement}")
    print("=" * 70)


if __name__ == "__main__":
    main()
