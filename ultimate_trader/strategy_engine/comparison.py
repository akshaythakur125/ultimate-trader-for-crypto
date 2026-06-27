import uuid

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig, TradeDirection, TradePlan
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator
from ultimate_trader.strategy_engine.engine import StrategyEngine
from ultimate_trader.strategy_engine.models import ComparisonResult, StrategyCandidate, StrategyConfig


def _compute_metrics(trades: list) -> dict[str, float]:
    if not trades:
        return {"total_trades": 0.0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "total_pnl": 0.0,
                "avg_pnl": 0.0, "max_drawdown_pct": 0.0, "avg_r_multiple": 0.0}

    wins = sum(1 for t in trades if getattr(t, "pnl", 0.0) > 0)
    losses = sum(1 for t in trades if getattr(t, "pnl", 0.0) <= 0)
    total = len(trades)

    pnls = [getattr(t, "pnl", 0.0) for t in trades]
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    rr_list = [getattr(t, "r_multiple", 0.0) for t in trades]
    equity_curve = []

    equity = 10000.0
    for t in trades:
        equity += getattr(t, "pnl", 0.0)
        equity_curve.append(equity)

    peak = max(equity_curve) if equity_curve else equity
    drawdown_pcts = []
    for eq in equity_curve:
        dd = (peak - eq) / peak * 100 if peak > 0 else 0.0
        drawdown_pcts.append(dd)

    metrics: dict[str, float] = {
        "total_trades": float(total),
        "win_rate": (wins / total * 100) if total > 0 else 0.0,
        "expectancy": sum(rr_list) / total if total > 0 else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "total_pnl": sum(pnls),
        "avg_pnl": sum(pnls) / total if total > 0 else 0.0,
        "max_drawdown_pct": max(drawdown_pcts) if drawdown_pcts else 0.0,
        "avg_r_multiple": sum(rr_list) / total if total > 0 else 0.0,
    }
    return metrics


def run_comparison(
    candles: list[HistoricalCandle],
    lsm_data_provider,
    config: StrategyConfig | None = None,
    old_replay_config: ReplayConfig | None = None,
    new_replay_config: ReplayConfig | None = None,
) -> ComparisonResult:
    strategy_config = config or StrategyConfig()
    rcfg_old = old_replay_config or ReplayConfig(
        taker_fee_percent=0.04, slippage_percent=0.02,
        funding_per_candle_percent=0.001, warmup_candles=50,
    )
    rcfg_new = new_replay_config or rcfg_old

    warmup = rcfg_old.warmup_candles

    lsm_cache: list[dict] = []
    for i, candle in enumerate(candles):
        lsm_data: dict = {}
        if lsm_data_provider:
            try:
                lsm_data = lsm_data_provider(candle, i)
            except Exception:
                pass
        lsm_cache.append(lsm_data)

    old_sim = TradeSimulator(rcfg_old)
    for i, candle in enumerate(candles):
        if i < warmup:
            continue
        lsm_data = lsm_cache[i]
        direction = TradeDirection.LONG
        entry_price = candle.close
        stop_loss_price = candle.close - (candle.high - candle.low) * 1.5
        target_price = candle.close + (candle.high - candle.low) * 1.5 * 3.0
        if lsm_data.get("direction") == "SHORT":
            direction = TradeDirection.SHORT
            stop_loss_price = candle.close + (candle.high - candle.low) * 1.5
            target_price = candle.close - (candle.high - candle.low) * 1.5 * 3.0
        if lsm_data.get("trade_permission") == "ALLOW":
            plan = TradePlan(
                plan_id=f"OP-{uuid.uuid4().hex[:8].upper()}",
                symbol=candle.symbol, direction=direction,
                signal_time=candle.timestamp,
                entry_zone_high=entry_price + (candle.high - candle.low) * 0.1,
                entry_zone_low=entry_price - (candle.high - candle.low) * 0.1,
                stop_loss=stop_loss_price, target_price=target_price,
                plan_reason="LSM permission",
            )
        else:
            plan = None
        from ultimate_trader.liquidity_smart_money.models import Candle as LsmCandle
        lc = LsmCandle(symbol=candle.symbol, timeframe=candle.timeframe,
                       timestamp=candle.timestamp, open=candle.open,
                       high=candle.high, low=candle.low, close=candle.close,
                       volume=candle.volume)
        old_sim.process_candle(lc, [plan] if plan else [])

    engine = StrategyEngine(strategy_config)
    new_sim = TradeSimulator(rcfg_new)
    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < warmup:
            continue
        lsm_data = lsm_cache[i]
        direction = TradeDirection.LONG
        entry_price = candle.close
        stop_loss_price = candle.close - (candle.high - candle.low) * 1.5
        target_price = candle.close + (candle.high - candle.low) * 1.5 * 3.0
        if lsm_data.get("direction") == "SHORT":
            direction = TradeDirection.SHORT
            stop_loss_price = candle.close + (candle.high - candle.low) * 1.5
            target_price = candle.close - (candle.high - candle.low) * 1.5 * 3.0
        candidate = engine.evaluate(candle=candle, lsm_data=lsm_data,
                                    direction=direction, entry_price=entry_price,
                                    stop_loss=stop_loss_price, target_price=target_price)
        plan = None
        if candidate is not None:
            plan = TradePlan(
                plan_id=f"NP-{uuid.uuid4().hex[:8].upper()}",
                symbol=candle.symbol, direction=direction,
                signal_time=candle.timestamp,
                entry_zone_high=entry_price + (candle.high - candle.low) * 0.1,
                entry_zone_low=entry_price - (candle.high - candle.low) * 0.1,
                stop_loss=stop_loss_price, target_price=target_price,
                plan_reason=f"Strategy confidence={candidate.total_confidence:.1f}",
            )
        from ultimate_trader.liquidity_smart_money.models import Candle as LsmCandle
        lc = LsmCandle(symbol=candle.symbol, timeframe=candle.timeframe,
                       timestamp=candle.timestamp, open=candle.open,
                       high=candle.high, low=candle.low, close=candle.close,
                       volume=candle.volume)
        new_sim.process_candle(lc, [plan] if plan else [])

    old_metrics = _compute_metrics(old_sim.completed_trades)
    new_metrics = _compute_metrics(new_sim.completed_trades)

    wr_change = new_metrics["win_rate"] - old_metrics["win_rate"]
    exp_change = new_metrics["expectancy"] - old_metrics["expectancy"]
    pf_old = old_metrics["profit_factor"]
    pf_new = new_metrics["profit_factor"]
    pf_change = ((pf_new - pf_old) / pf_old * 100) if pf_old and pf_old != float("inf") else 0.0
    dd_change = new_metrics["max_drawdown_pct"] - old_metrics["max_drawdown_pct"]

    improvement_desc = (
        f"Win rate: {old_metrics['win_rate']:.1f}% -> {new_metrics['win_rate']:.1f}% ({wr_change:+.1f}%), "
        f"Expectancy: {old_metrics['expectancy']:.2f}R -> {new_metrics['expectancy']:.2f}R ({exp_change:+.2f}R), "
        f"Profit factor: {pf_old:.2f} -> {pf_new:.2f}"
    )

    return ComparisonResult(
        old_engine="LSM Only", new_engine="Strategy Engine",
        old_trades=len(old_sim.completed_trades), new_trades=len(new_sim.completed_trades),
        old_win_rate=old_metrics["win_rate"], new_win_rate=new_metrics["win_rate"],
        old_expectancy=old_metrics["expectancy"], new_expectancy=new_metrics["expectancy"],
        old_profit_factor=pf_old, new_profit_factor=pf_new,
        old_max_drawdown=old_metrics["max_drawdown_pct"],
        new_max_drawdown=new_metrics["max_drawdown_pct"],
        win_rate_change=wr_change, expectancy_change=exp_change,
        profit_factor_change=pf_change, drawdown_change=dd_change,
        improvement=improvement_desc,
    )
