import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

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
from ultimate_trader.backtest_forensics.diagnostic_builder import build_trade_diagnostics
from ultimate_trader.backtest_forensics.forensic_report import ForensicReport
from ultimate_trader.backtest_forensics.outcome_analyzer import OutcomeAnalyzer

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "historical", "BTCUSDT_15m.csv")


def build_lsm_provider():
    swing = SwingDetector(lookback=5)
    pools = LiquidityPoolDetector()
    sweep_det = SweepDetector()
    structure = MarketStructureEngine(lookback=5)
    fvg_det = FairValueGapDetector(min_gap_bps=0.5)
    ob_det = OrderBlockDetector()
    pd_eng = PremiumDiscountEngine()
    disp_eng = DisplacementEngine()
    conf_eng = ConfluenceEngine()
    candles_lsm = []

    def provider(candle, idx):
        lc = LsmCandle(symbol=candle.symbol, timeframe=candle.timeframe,
                       timestamp=candle.timestamp, open=candle.open,
                       high=candle.high, low=candle.low, close=candle.close,
                       volume=candle.volume)
        candles_lsm.append(lc)
        swing.add_candle(lc)
        sh, sl, eh, el = (swing.get_swing_highs(), swing.get_swing_lows(),
                          swing.get_equal_highs(), swing.get_equal_lows())
        zones = pools.analyze(sh, sl, eh, el, candle.close, [])
        sw = sweep_det.analyze(candles_lsm[-5:], zones)
        se = structure.analyze(sh, sl, candles_lsm[-10:])
        fvgs = fvg_det.analyze(candles_lsm[-5:])
        obs = ob_det.analyze(candles_lsm[-5:], fvgs)
        pd_state = pd_eng.analyze(sh, sl, candle.close)
        disp_result = disp_eng.analyze(candles_lsm[-5:])
        conf_result = conf_eng.analyze(zones, sw, se, fvgs, obs, pd_state,
                                        [disp_result] if disp_result else [])
        return {
            "direction": "LONG" if conf_result.directional_bias.value in ("LONG",) else "SHORT",
            "trade_permission": conf_result.trade_permission,
            "confluence_score": conf_result.confluence_score,
            "sweeps": sw, "structure_events": se, "fvgs": fvgs,
            "order_blocks": obs, "risk_score": 0.0,
        }
    return provider


def main():
    print("=" * 70)
    print("Ultimate Trader -- Backtest Forensics & Trade Outcome Diagnostics")
    print("=" * 70)

    csv_path = os.path.abspath(CSV_PATH)
    if not os.path.exists(csv_path):
        print(f"Error: CSV not found at {csv_path}")
        sys.exit(1)

    print(f"\nLoading data from: {csv_path}")
    loader = HistoricalDataLoader()
    candles = loader.load_csv(csv_path)
    print(f"Candles loaded: {len(candles)}")

    config = StrategyConfig(confidence_threshold=60.0)
    rcfg = ReplayConfig(warmup_candles=50, taker_fee_percent=0.04,
                         slippage_percent=0.02, funding_per_candle_percent=0.001)

    lsm_provider = build_lsm_provider()

    print("\nRunning comparison replay...")
    result, old_trades, new_trades = run_comparison(candles, lsm_provider, config, rcfg, rcfg, return_trades=True)

    diagnostics = []
    for t in new_trades if new_trades else old_trades:
        td = build_trade_diagnostics(t)
        diagnostics.append(td)

    outcome = OutcomeAnalyzer().analyze(diagnostics)
    report = ForensicReport.generate(diagnostics)

    print("\n" + "=" * 70)
    print("FORENSIC REPORT")
    print("=" * 70)
    print(f"  Total trades analyzed:     {report.total_trades_analyzed}")
    print(f"  Win rate:                  {report.win_rate:.1f}%")
    print(f"  Expectancy (R):            {report.expectancy:.2f}")
    print(f"  Avg trades/day:            {outcome.total_trades / max(1, len(set(t.signal_time.strftime('%Y-%m-%d') for t in diagnostics))):.1f}")
    print(f"  Stopped within 1 candle:   {outcome.stopped_within_1_candle_pct:.1f}%")
    print(f"  Same-candle stop-first:    {outcome.same_candle_stop_first_pct:.1f}%")

    print(f"\n  Top 5 failure causes:")
    for i, cause in enumerate(report.top_5_failure_causes[:5], 1):
        print(f"    {i}. {cause}")

    print(f"\n  Stop/target problems:")
    for p in report.stop_target_problems[:3]:
        print(f"    - {p}")

    print(f"\n  Overtrading status:        {report.overtrading_status}")
    print(f"  Filter contribution:       {report.filter_contribution_summary}")
    print(f"  Results reliable:          {report.results_reliable}")
    print(f"  Simulator bug suspected:   {report.simulator_bug_suspected}")

    print(f"\n  Recommended next fixes:")
    for i, fix in enumerate(report.recommended_next_fixes[:5], 1):
        print(f"    {i}. {fix}")

    print(f"\n  Final conclusion:")
    if report.simulator_bug_suspected:
        print("    SIMULATOR BUG DETECTED — review entry/stop fill ordering before trusting results")
    elif report.results_reliable:
        print("    Results appear reliable. Improvements should focus on stop placement and entry timing.")
    else:
        print("    Results may be unreliable due to overtrading or excessive same-candle stop-outs.")

    print("=" * 70)


if __name__ == "__main__":
    main()
