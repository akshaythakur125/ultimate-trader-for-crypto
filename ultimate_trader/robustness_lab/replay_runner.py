import csv
import os
import sys
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ultimate_trader.historical_replay.models import HistoricalCandle, ReplayConfig, TradeDirection, TradePlan
from ultimate_trader.historical_replay.trade_simulator import TradeSimulator
from ultimate_trader.liquidity_smart_money import Candle as LsmCandle
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig, freeze_current_config
from ultimate_trader.selectivity_engine import CandidateRanker, DailySelector, DailySelectorConfig, QualityGate, QualityGateConfig, RejectionReasonAnalyzer
from ultimate_trader.strategy_engine.engine import StrategyEngine
from ultimate_trader.strategy_engine.models import StrategyConfig
from ultimate_trader.drawdown_control import RiskGovernor, RiskGovernorConfig
from ultimate_trader.regime_filter import RegimeGate, RegimeGateConfig


BINGX_API = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "historical")


CSV_COLUMNS = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]


def _fetch_klines(symbol: str, interval: str, days: int = 90):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = now_ms - days * 24 * 60 * 60 * 1000
    all_items = []
    cursor = start_ms
    while cursor < now_ms:
        resp = requests.get(BINGX_API, params={
            "symbol": symbol, "interval": interval,
            "limit": 500, "startTime": cursor,
        }, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"API error {body.get('code')}")
        items = body.get("data", [])
        if not items:
            break
        all_items.extend(items)
        newest = int(items[0]["time"])
        if newest >= now_ms:
            break
        cursor = newest + 1
    return all_items


def _items_to_csv(items, symbol: str, timeframe: str, output_path: str):
    seen = set()
    rows = []
    for item in items:
        ts = datetime.fromtimestamp(int(item["time"]) / 1000, tz=timezone.utc)
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        if ts_str in seen:
            continue
        seen.add(ts_str)
        rows.append({
            "symbol": symbol, "timeframe": timeframe,
            "timestamp": ts_str, "open": item["open"],
            "high": item["high"], "low": item["low"],
            "close": item["close"], "volume": item["volume"],
        })
    rows.sort(key=lambda r: r["timestamp"])
    with open(output_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def _csv_path(symbol: str, timeframe: str) -> str:
    return os.path.join(DATA_DIR, f"{symbol}_{timeframe}.csv")


def load_candles_from_csv(path: str) -> list[HistoricalCandle]:
    candles = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                candles.append(HistoricalCandle(
                    symbol=row.get("symbol", "BTCUSDT"),
                    timeframe=row.get("timeframe", "15m"),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                ))
            except (KeyError, ValueError):
                continue
    return candles


def ensure_data(symbol: str, timeframe: str, days: int = 90) -> list[HistoricalCandle]:
    path = _csv_path(symbol, timeframe)
    if os.path.exists(path):
        return load_candles_from_csv(path)
    api_symbol = symbol.replace("USDT", "-USDT")
    for attempt_days in [365, days, 180, 90, 60, 30, 14, 7]:
        print(f"  Downloading {api_symbol} {timeframe} ({attempt_days}d)...")
        try:
            items = _fetch_klines(api_symbol, timeframe, days=attempt_days)
            if not items:
                print(f"  No data available for {attempt_days}d range")
                continue
            count = _items_to_csv(items, symbol, timeframe, path)
            print(f"  Saved {count} candles to {os.path.basename(path)}")
            return load_candles_from_csv(path)
        except Exception as e:
            print(f"  Cannot download {symbol} {timeframe}: {e}")
            continue
    print(f"  Giving up on {symbol} {timeframe}")
    return []


def run_selective_replay(
    candles: list[HistoricalCandle],
    frozen_cfg: FrozenConfig,
    rcfg: ReplayConfig,
    invert: bool = False,
    collect_trade_timestamps: bool = False,
) -> tuple[dict[str, Any], RejectionReasonAnalyzer, dict[str, int]]:
    strat_cfg = StrategyConfig(confidence_threshold=frozen_cfg.strategy_confidence_threshold)
    engine = StrategyEngine(strat_cfg)
    sim = TradeSimulator(rcfg)
    ranker = CandidateRanker()
    qg_cfg = QualityGateConfig(
        min_confluence_score=frozen_cfg.min_confluence_score,
        min_directional_confidence=frozen_cfg.min_directional_confidence,
        max_conflict_score=frozen_cfg.max_conflict_score,
        max_reversal_risk_score=frozen_cfg.max_reversal_risk_score,
        max_risk_score=frozen_cfg.max_risk_score,
        min_rr=frozen_cfg.min_rr,
        allowed_grades=set(frozen_cfg.allowed_grades),
    )
    qg = QualityGate(qg_cfg)
    ds_cfg = DailySelectorConfig(
        target_trades_per_day=frozen_cfg.target_trades_per_day,
        hard_max_per_day=frozen_cfg.hard_max_per_day,
        same_symbol_cooldown_minutes=frozen_cfg.same_symbol_cooldown_minutes,
        same_direction_cooldown_minutes=frozen_cfg.same_direction_cooldown_minutes,
        loss_threshold_increase=frozen_cfg.loss_threshold_increase,
        max_losses_per_day=frozen_cfg.max_losses_per_day,
    )
    sel = DailySelector(qg, ds_cfg)
    ra = RejectionReasonAnalyzer()

    lsm_pipeline = _LsmPipeline()

    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < rcfg.warmup_candles:
            lsm_pipeline.process_candle(candle)
            continue

        lsm_data, conf_result = lsm_pipeline.process_candle(candle)
        direction_str = lsm_data.get("direction", "NEUTRAL")

        if invert:
            direction_str = "SHORT" if direction_str == "LONG" else ("LONG" if direction_str == "SHORT" else "NEUTRAL")

        if direction_str == "NEUTRAL":
            continue

        direction = TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT
        entry = candle.close

        if stop_method == "baseline":
            cr = candle.high - candle.low
            stop_dist = cr * 1.5
        elif stop_method in ("avg5", "avg10", "avg20"):
            n = int(stop_method.replace("avg", ""))
            recent = list(range_buffer)[-n:] if len(range_buffer) >= n else list(range_buffer)
            avg = sum(recent) / len(recent)
            stop_dist = avg * 1.5
        elif stop_method == "structure":
            cr = candle.high - candle.low
            swing_highs = lsm_data.get("swing_highs", [])
            swing_lows = lsm_data.get("swing_lows", [])
            stop_dist = None
            if direction == TradeDirection.LONG and swing_lows:
                below = [s for s in swing_lows if _swing_price(s) < entry]
                if below:
                    nearest = max(below, key=_swing_price)
                    stop_dist = entry - (_swing_price(nearest) - cr * 0.3)
            elif direction == TradeDirection.SHORT and swing_highs:
                above = [s for s in swing_highs if _swing_price(s) > entry]
                if above:
                    nearest = min(above, key=_swing_price)
                    stop_dist = _swing_price(nearest) + cr * 0.3 - entry
            if stop_dist is None or stop_dist < cr * 0.5:
                stop_dist = cr * 1.5
        elif stop_method == "hybrid":
            cr = candle.high - candle.low
            base_dist = cr * 1.5
            swing_highs = lsm_data.get("swing_highs", [])
            swing_lows = lsm_data.get("swing_lows", [])
            struct_dist = None
            if direction == TradeDirection.LONG and swing_lows:
                below = [s for s in swing_lows if _swing_price(s) < entry]
                if below:
                    nearest = max(below, key=_swing_price)
                    struct_dist = entry - (_swing_price(nearest) - cr * 0.3)
            elif direction == TradeDirection.SHORT and swing_highs:
                above = [s for s in swing_highs if _swing_price(s) > entry]
                if above:
                    nearest = min(above, key=_swing_price)
                    struct_dist = _swing_price(nearest) + cr * 0.3 - entry
            if struct_dist is None:
                struct_dist = base_dist
            stop_dist = max(base_dist, min(struct_dist, base_dist * 3.0 / 2.5))
        else:
            cr = candle.high - candle.low
            stop_dist = cr * 1.5

        stop = entry - stop_dist if direction == TradeDirection.LONG else entry + stop_dist
        target = entry + stop_dist * 3.0 if direction == TradeDirection.LONG else entry - stop_dist * 3.0

        lsm_data["direction"] = direction_str
        candidate = engine.evaluate(candle=candle, lsm_data=lsm_data, direction=direction, entry_price=entry, stop_loss=stop, target_price=target)
        if candidate is None:
            continue

        rc = ranker.rank(candidate, conf_result)
        sel.register_candidate(rc)
        day_key = candle.timestamp.strftime("%Y-%m-%d")
        results = sel.select_for_day(day_key)

        for rc2, sr in results:
            if not sr.allowed:
                ra.record(rc2.candidate_id, sr.rejection_category, sr.rejection_reason)
                continue
            plan = TradePlan(
                plan_id=f"RP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                direction=direction, signal_time=candle.timestamp,
                entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
                stop_loss=stop, target_price=target,
            )
            trades = sim.process_candle(hc_to_lsm(candle), [plan])
            for t in trades:
                sel.record_outcome(getattr(t, "trade_id", rc2.candidate_id), t.net_r > 0, day_key)

    daily_breakdown = defaultdict(int)
    for t in sim.completed_trades:
        ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
        if ts:
            daily_breakdown[ts.strftime("%Y-%m-%d")] += 1

    metrics = compute_metrics(sim.completed_trades)
    if collect_trade_timestamps:
        timestamps = []
        for t in sim.completed_trades:
            ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
            if ts:
                timestamps.append(ts.timestamp())
        metrics["trade_timestamps"] = timestamps
    return metrics, ra, dict(daily_breakdown)


def run_selective_replay_with_governor(
    candles: list[HistoricalCandle],
    frozen_cfg: FrozenConfig,
    rcfg: ReplayConfig,
    gov_cfg: Optional[RiskGovernorConfig] = None,
    invert: bool = False,
) -> tuple[dict[str, Any], RejectionReasonAnalyzer, dict[str, int], dict[str, int]]:
    strat_cfg = StrategyConfig(confidence_threshold=frozen_cfg.strategy_confidence_threshold)
    engine = StrategyEngine(strat_cfg)
    sim = TradeSimulator(rcfg)
    ranker = CandidateRanker()
    qg_cfg = QualityGateConfig(
        min_confluence_score=frozen_cfg.min_confluence_score,
        min_directional_confidence=frozen_cfg.min_directional_confidence,
        max_conflict_score=frozen_cfg.max_conflict_score,
        max_reversal_risk_score=frozen_cfg.max_reversal_risk_score,
        max_risk_score=frozen_cfg.max_risk_score,
        min_rr=frozen_cfg.min_rr,
        allowed_grades=set(frozen_cfg.allowed_grades),
    )
    qg = QualityGate(qg_cfg)
    ds_cfg = DailySelectorConfig(
        target_trades_per_day=frozen_cfg.target_trades_per_day,
        hard_max_per_day=frozen_cfg.hard_max_per_day,
        same_symbol_cooldown_minutes=frozen_cfg.same_symbol_cooldown_minutes,
        same_direction_cooldown_minutes=frozen_cfg.same_direction_cooldown_minutes,
        loss_threshold_increase=frozen_cfg.loss_threshold_increase,
        max_losses_per_day=frozen_cfg.max_losses_per_day,
    )
    sel = DailySelector(qg, ds_cfg)
    ra = RejectionReasonAnalyzer()
    gov = RiskGovernor(gov_cfg or RiskGovernorConfig())
    gov_stats = {"daily_loss": 0, "weekly_loss": 0, "drawdown_mode": 0, "rolling_perf": 0, "consecutive_losses": 0}

    lsm_pipeline = _LsmPipeline()

    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < rcfg.warmup_candles:
            lsm_pipeline.process_candle(candle)
            continue

        lsm_data, conf_result = lsm_pipeline.process_candle(candle)
        direction_str = lsm_data.get("direction", "NEUTRAL")

        if invert:
            direction_str = "SHORT" if direction_str == "LONG" else ("LONG" if direction_str == "SHORT" else "NEUTRAL")

        if direction_str == "NEUTRAL":
            continue

        direction = TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT
        entry = candle.close
        cr = candle.high - candle.low
        stop = candle.close - cr * 1.5 if direction == TradeDirection.LONG else candle.close + cr * 1.5
        target = candle.close + cr * 1.5 * 3.0 if direction == TradeDirection.LONG else candle.close - cr * 1.5 * 3.0

        lsm_data["direction"] = direction_str
        candidate = engine.evaluate(candle=candle, lsm_data=lsm_data, direction=direction, entry_price=entry, stop_loss=stop, target_price=target)
        if candidate is None:
            continue

        rc = ranker.rank(candidate, conf_result)
        sel.register_candidate(rc)
        day_key = candle.timestamp.strftime("%Y-%m-%d")
        results = sel.select_for_day(day_key)

        for rc2, sr in results:
            if not sr.allowed:
                ra.record(rc2.candidate_id, sr.rejection_category, sr.rejection_reason)
                continue
            grade = rc2.rank_grade if hasattr(rc2, "rank_grade") else rc.grade
            dec = gov.check_state(candle.timestamp, grade=grade)
            if not dec.allowed:
                if "daily loss" in dec.rejection_reason:
                    gov_stats["daily_loss"] += 1
                elif "weekly loss" in dec.rejection_reason:
                    gov_stats["weekly_loss"] += 1
                elif "consecutive" in dec.rejection_reason:
                    gov_stats["consecutive_losses"] += 1
                elif "EV" in dec.rejection_reason or "PF" in dec.rejection_reason:
                    gov_stats["rolling_perf"] += 1
                else:
                    gov_stats["drawdown_mode"] += 1
                continue
            plan = TradePlan(
                plan_id=f"RP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                direction=direction, signal_time=candle.timestamp,
                entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
                stop_loss=stop, target_price=target,
            )
            trades = sim.process_candle(hc_to_lsm(candle), [plan])
            for t in trades:
                sel.record_outcome(getattr(t, "trade_id", rc2.candidate_id), t.net_r > 0, day_key)
                if t.net_r != 0.0:
                    gov.evaluate(t, grade=grade)

    daily_breakdown = defaultdict(int)
    for t in sim.completed_trades:
        ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
        if ts:
            daily_breakdown[ts.strftime("%Y-%m-%d")] += 1

    return compute_metrics(sim.completed_trades), ra, dict(daily_breakdown), gov_stats


def _swing_price(sp):
    return sp.price if hasattr(sp, 'price') else (sp.get('price', 0) if isinstance(sp, dict) else 0)

def run_selective_replay_with_regime(
    candles: list[HistoricalCandle],
    frozen_cfg: FrozenConfig,
    rcfg: ReplayConfig,
    regime_gate: RegimeGate,
    invert: bool = False,
    collect_trade_timestamps: bool = False,
    diagnose: bool = False,
    stop_method: str = "atr14_20",
    entry_method: str = "immediate",
) -> tuple[dict[str, Any], RejectionReasonAnalyzer, dict[str, int], dict[str, int]]:
    strat_cfg = StrategyConfig(confidence_threshold=frozen_cfg.strategy_confidence_threshold)
    engine = StrategyEngine(strat_cfg)
    sim = TradeSimulator(rcfg)
    ranker = CandidateRanker()
    qg_cfg = QualityGateConfig(
        min_confluence_score=frozen_cfg.min_confluence_score,
        min_directional_confidence=frozen_cfg.min_directional_confidence,
        max_conflict_score=frozen_cfg.max_conflict_score,
        max_reversal_risk_score=frozen_cfg.max_reversal_risk_score,
        max_risk_score=frozen_cfg.max_risk_score,
        min_rr=frozen_cfg.min_rr,
        allowed_grades=set(frozen_cfg.allowed_grades),
    )
    qg = QualityGate(qg_cfg)
    ds_cfg = DailySelectorConfig(
        target_trades_per_day=frozen_cfg.target_trades_per_day,
        hard_max_per_day=frozen_cfg.hard_max_per_day,
        same_symbol_cooldown_minutes=frozen_cfg.same_symbol_cooldown_minutes,
        same_direction_cooldown_minutes=frozen_cfg.same_direction_cooldown_minutes,
        loss_threshold_increase=frozen_cfg.loss_threshold_increase,
        max_losses_per_day=frozen_cfg.max_losses_per_day,
    )
    sel = DailySelector(qg, ds_cfg)
    ra = RejectionReasonAnalyzer()
    regime_stats = {"regime_blocked": 0, "regime_scores": []}
    regime_gate.reset_classifier()
    signal_contexts: dict[float, tuple[dict, Any, Any]] = {}
    pending_signals: list[dict] = []

    lsm_pipeline = _LsmPipeline()
    range_buffer = deque(maxlen=20)
    true_range_buffer = deque(maxlen=14)

    for i, candle in enumerate(candles):
        if i > 0:
            tr = max(candle.high - candle.low, abs(candle.high - candles[i - 1].close), abs(candle.low - candles[i - 1].close))
            true_range_buffer.append(tr)
        if entry_method in ("confirm_1c", "no_reverse_0.5r", "confirm_direction"):
            for ps in list(pending_signals):
                # Only check the candle immediately after the signal (index + 1)
                if i != ps["signal_index"] + 1:
                    continue
                sig_dir = ps["direction"]
                confirmed = False
                if entry_method == "confirm_1c":
                    confirmed = True
                elif entry_method == "no_reverse_0.5r":
                    half_r = ps["stop_dist"] * 0.5
                    if sig_dir == TradeDirection.LONG:
                        worst = min(candle.low, candle.open)
                        if worst >= ps["entry"] - half_r:
                            confirmed = True
                    else:
                        worst = max(candle.high, candle.open)
                        if worst <= ps["entry"] + half_r:
                            confirmed = True
                elif entry_method == "confirm_direction":
                    if sig_dir == TradeDirection.LONG and candle.close > candle.open:
                        confirmed = True
                    elif sig_dir == TradeDirection.SHORT and candle.close < candle.open:
                        confirmed = True
                if confirmed:
                    new_entry = candle.close
                    new_cr = candle.high - candle.low
                    plan = TradePlan(
                        plan_id=f"RP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                        direction=sig_dir, signal_time=ps["signal_time"],
                        entry_zone_high=new_entry + new_cr * 0.1,
                        entry_zone_low=new_entry - new_cr * 0.1,
                        stop_loss=ps["stop"], target_price=ps["target"],
                    )
                    trades = sim.process_candle(hc_to_lsm(candle), [plan])
                    for t in trades:
                        sel.record_outcome(getattr(t, "trade_id", ps["candidate_id"]), t.net_r > 0, ps["day_key"])
                pending_signals.remove(ps)

        range_buffer.append(candle.high - candle.low)
        engine.add_candle(candle)
        if i < rcfg.warmup_candles:
            lsm_pipeline.process_candle(candle)
            continue

        lsm_data, conf_result = lsm_pipeline.process_candle(candle)
        direction_str = lsm_data.get("direction", "NEUTRAL")

        if invert:
            direction_str = "SHORT" if direction_str == "LONG" else ("LONG" if direction_str == "SHORT" else "NEUTRAL")

        if direction_str == "NEUTRAL":
            continue

        gate_dec = regime_gate.check(candle, lsm_data, conf_result)
        regime_stats["regime_scores"].append(gate_dec.similarity_score)
        if not gate_dec.allowed:
            regime_stats["regime_blocked"] += 1
            continue

        direction = TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT
        entry = candle.close
        cr = candle.high - candle.low

        if stop_method == "baseline":
            stop_dist = cr * 1.5
        elif stop_method == "wide20":
            stop_dist = cr * 2.0
        elif stop_method == "wide25":
            stop_dist = cr * 2.5
        elif stop_method == "atr14_15":
            atr_val = sum(true_range_buffer) / max(len(true_range_buffer), 1) if true_range_buffer else cr
            stop_dist = atr_val * 1.5
        elif stop_method == "atr14_20":
            atr_val = sum(true_range_buffer) / max(len(true_range_buffer), 1) if true_range_buffer else cr
            stop_dist = atr_val * 2.0
        elif stop_method in ("avg5", "avg10", "avg20"):
            n = int(stop_method.replace("avg", ""))
            recent = list(range_buffer)[-n:] if len(range_buffer) >= n else list(range_buffer)
            avg = sum(recent) / len(recent)
            stop_dist = avg * 1.5
        elif stop_method == "structure":
            swing_highs = lsm_data.get("swing_highs", [])
            swing_lows = lsm_data.get("swing_lows", [])
            stop_dist = None
            if direction == TradeDirection.LONG and swing_lows:
                below = [s for s in swing_lows if _swing_price(s) < entry]
                if below:
                    nearest = max(below, key=_swing_price)
                    stop_dist = entry - (_swing_price(nearest) - cr * 0.3)
            elif direction == TradeDirection.SHORT and swing_highs:
                above = [s for s in swing_highs if _swing_price(s) > entry]
                if above:
                    nearest = min(above, key=_swing_price)
                    stop_dist = _swing_price(nearest) + cr * 0.3 - entry
            if stop_dist is None or stop_dist < cr * 0.5:
                stop_dist = cr * 1.5
        elif stop_method == "hybrid":
            base_dist = cr * 1.5
            swing_highs = lsm_data.get("swing_highs", [])
            swing_lows = lsm_data.get("swing_lows", [])
            struct_dist = None
            if direction == TradeDirection.LONG and swing_lows:
                below = [s for s in swing_lows if _swing_price(s) < entry]
                if below:
                    nearest = max(below, key=_swing_price)
                    struct_dist = entry - (_swing_price(nearest) - cr * 0.3)
            elif direction == TradeDirection.SHORT and swing_highs:
                above = [s for s in swing_highs if _swing_price(s) > entry]
                if above:
                    nearest = min(above, key=_swing_price)
                    struct_dist = _swing_price(nearest) + cr * 0.3 - entry
            if struct_dist is None:
                struct_dist = base_dist
            stop_dist = max(base_dist, min(struct_dist, base_dist * 3.0 / 2.5))
        elif stop_method == "avg5_hybrid":
            n = 5
            recent = list(range_buffer)[-n:] if len(range_buffer) >= n else list(range_buffer)
            avg_cr = sum(recent) / len(recent)
            base_dist = avg_cr * 1.5
            swing_highs = lsm_data.get("swing_highs", [])
            swing_lows = lsm_data.get("swing_lows", [])
            struct_dist = None
            if direction == TradeDirection.LONG and swing_lows:
                below = [s for s in swing_lows if _swing_price(s) < entry]
                if below:
                    nearest = max(below, key=_swing_price)
                    struct_dist = entry - (_swing_price(nearest) - avg_cr * 0.3)
            elif direction == TradeDirection.SHORT and swing_highs:
                above = [s for s in swing_highs if _swing_price(s) > entry]
                if above:
                    nearest = min(above, key=_swing_price)
                    struct_dist = _swing_price(nearest) + avg_cr * 0.3 - entry
            if struct_dist is None:
                struct_dist = base_dist
            stop_dist = max(base_dist, min(struct_dist, base_dist * 3.0 / 2.5))
        else:
            stop_dist = cr * 1.5

        stop = entry - stop_dist if direction == TradeDirection.LONG else entry + stop_dist
        target = entry + stop_dist * 3.0 if direction == TradeDirection.LONG else entry - stop_dist * 3.0

        lsm_data["direction"] = direction_str
        candidate = engine.evaluate(candle=candle, lsm_data=lsm_data, direction=direction, entry_price=entry, stop_loss=stop, target_price=target)
        if candidate is None:
            continue

        rc = ranker.rank(candidate, conf_result)
        sel.register_candidate(rc)
        day_key = candle.timestamp.strftime("%Y-%m-%d")
        results = sel.select_for_day(day_key)

        for rc2, sr in results:
            if not sr.allowed:
                ra.record(rc2.candidate_id, sr.rejection_category, sr.rejection_reason)
                continue
            if diagnose:
                signal_contexts[candle.timestamp.timestamp()] = (dict(lsm_data), gate_dec)
            if entry_method == "immediate":
                plan = TradePlan(
                    plan_id=f"RP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                    direction=direction, signal_time=candle.timestamp,
                    entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
                    stop_loss=stop, target_price=target,
                )
                trades = sim.process_candle(hc_to_lsm(candle), [plan])
                for t in trades:
                    sel.record_outcome(getattr(t, "trade_id", rc2.candidate_id), t.net_r > 0, day_key)
            elif entry_method == "skip_low_volatility":
                recent = list(range_buffer)[-5:] if len(range_buffer) >= 5 else list(range_buffer)
                sorted_ranges = sorted(recent)
                med = sorted_ranges[len(sorted_ranges) // 2]
                if cr >= med:
                    plan = TradePlan(
                        plan_id=f"RP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                        direction=direction, signal_time=candle.timestamp,
                        entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
                        stop_loss=stop, target_price=target,
                    )
                    trades = sim.process_candle(hc_to_lsm(candle), [plan])
                    for t in trades:
                        sel.record_outcome(getattr(t, "trade_id", rc2.candidate_id), t.net_r > 0, day_key)
            else:
                pending_signals.append({
                    "direction": direction, "entry": entry, "stop": stop,
                    "target": target, "signal_time": candle.timestamp,
                    "stop_dist": stop_dist, "candidate_id": rc2.candidate_id,
                    "day_key": day_key, "signal_index": i,
                })

    daily_breakdown = defaultdict(int)
    for t in sim.completed_trades:
        ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
        if ts:
            daily_breakdown[ts.strftime("%Y-%m-%d")] += 1

    re_metrics = compute_metrics(sim.completed_trades)
    if collect_trade_timestamps:
        timestamps = []
        for t in sim.completed_trades:
            ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
            if ts:
                timestamps.append(ts.timestamp())
        re_metrics["trade_timestamps"] = timestamps
    if diagnose:
        diagnostics = []
        for t in sim.completed_trades:
            ts = (getattr(t, "signal_time", None) or getattr(t, "entry_time", None))
            ctx = signal_contexts.get(ts.timestamp()) if ts else None
            lsm_ctx, gate_ctx = ctx if ctx else ({}, None)
            diagnostics.append({
                "timestamp": ts.isoformat() if ts else "",
                "direction": t.direction.value if hasattr(t.direction, "value") else str(t.direction),
                "net_r": t.net_r,
                "gross_r": t.gross_r,
                "exit_reason": t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason),
                "holding_candles": t.holding_candles,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "regime_score": gate_ctx.similarity_score if gate_ctx else None,
                "regime_allowed": gate_ctx.allowed if gate_ctx else None,
                "lsm_confluence": lsm_ctx.get("confluence_score"),
                "lsm_direction": lsm_ctx.get("direction"),
                "lsm_conflict": lsm_ctx.get("conflict_severity"),
                "sweep_bias": lsm_ctx.get("sweep_bias"),
                "structure_bias": lsm_ctx.get("structure_bias"),
                "fvg_bias": lsm_ctx.get("fvg_bias"),
                "order_block_bias": lsm_ctx.get("order_block_bias"),
                "premium_discount_bias": lsm_ctx.get("premium_discount_bias"),
                "displacement_bias": lsm_ctx.get("displacement_bias"),
                "microstructure_bias": lsm_ctx.get("microstructure_bias"),
                "orderflow_bias": lsm_ctx.get("orderflow_bias"),
                "trend_bias": lsm_ctx.get("trend_bias"),
            })
        re_metrics["trade_diagnostics"] = diagnostics
    return re_metrics, ra, dict(daily_breakdown), regime_stats


def run_selective_replay_with_regime_governor(
    candles: list[HistoricalCandle],
    frozen_cfg: FrozenConfig,
    rcfg: ReplayConfig,
    regime_gate: RegimeGate,
    gov_cfg: Optional[RiskGovernorConfig] = None,
    invert: bool = False,
) -> tuple[dict[str, Any], RejectionReasonAnalyzer, dict[str, int], dict[str, int], dict[str, int]]:
    strat_cfg = StrategyConfig(confidence_threshold=frozen_cfg.strategy_confidence_threshold)
    engine = StrategyEngine(strat_cfg)
    sim = TradeSimulator(rcfg)
    ranker = CandidateRanker()
    qg_cfg = QualityGateConfig(
        min_confluence_score=frozen_cfg.min_confluence_score,
        min_directional_confidence=frozen_cfg.min_directional_confidence,
        max_conflict_score=frozen_cfg.max_conflict_score,
        max_reversal_risk_score=frozen_cfg.max_reversal_risk_score,
        max_risk_score=frozen_cfg.max_risk_score,
        min_rr=frozen_cfg.min_rr,
        allowed_grades=set(frozen_cfg.allowed_grades),
    )
    qg = QualityGate(qg_cfg)
    ds_cfg = DailySelectorConfig(
        target_trades_per_day=frozen_cfg.target_trades_per_day,
        hard_max_per_day=frozen_cfg.hard_max_per_day,
        same_symbol_cooldown_minutes=frozen_cfg.same_symbol_cooldown_minutes,
        same_direction_cooldown_minutes=frozen_cfg.same_direction_cooldown_minutes,
        loss_threshold_increase=frozen_cfg.loss_threshold_increase,
        max_losses_per_day=frozen_cfg.max_losses_per_day,
    )
    sel = DailySelector(qg, ds_cfg)
    ra = RejectionReasonAnalyzer()
    gov = RiskGovernor(gov_cfg or RiskGovernorConfig())
    gov_stats = {"daily_loss": 0, "weekly_loss": 0, "drawdown_mode": 0, "rolling_perf": 0, "consecutive_losses": 0}
    regime_stats = {"regime_blocked": 0, "regime_scores": []}
    regime_gate.reset_classifier()

    lsm_pipeline = _LsmPipeline()

    for i, candle in enumerate(candles):
        engine.add_candle(candle)
        if i < rcfg.warmup_candles:
            lsm_pipeline.process_candle(candle)
            continue

        lsm_data, conf_result = lsm_pipeline.process_candle(candle)
        direction_str = lsm_data.get("direction", "NEUTRAL")

        if invert:
            direction_str = "SHORT" if direction_str == "LONG" else ("LONG" if direction_str == "SHORT" else "NEUTRAL")

        if direction_str == "NEUTRAL":
            continue

        gate_dec = regime_gate.check(candle, lsm_data, conf_result)
        regime_stats["regime_scores"].append(gate_dec.similarity_score)
        if not gate_dec.allowed:
            regime_stats["regime_blocked"] += 1
            continue

        direction = TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT
        entry = candle.close
        cr = candle.high - candle.low
        stop = candle.close - cr * 1.5 if direction == TradeDirection.LONG else candle.close + cr * 1.5
        target = candle.close + cr * 1.5 * 3.0 if direction == TradeDirection.LONG else candle.close - cr * 1.5 * 3.0

        lsm_data["direction"] = direction_str
        candidate = engine.evaluate(candle=candle, lsm_data=lsm_data, direction=direction, entry_price=entry, stop_loss=stop, target_price=target)
        if candidate is None:
            continue

        rc = ranker.rank(candidate, conf_result)
        sel.register_candidate(rc)
        day_key = candle.timestamp.strftime("%Y-%m-%d")
        results = sel.select_for_day(day_key)

        for rc2, sr in results:
            if not sr.allowed:
                ra.record(rc2.candidate_id, sr.rejection_category, sr.rejection_reason)
                continue
            grade = rc2.rank_grade if hasattr(rc2, "rank_grade") else rc.grade
            dec = gov.check_state(candle.timestamp, grade=grade)
            if not dec.allowed:
                if "daily loss" in dec.rejection_reason:
                    gov_stats["daily_loss"] += 1
                elif "weekly loss" in dec.rejection_reason:
                    gov_stats["weekly_loss"] += 1
                elif "consecutive" in dec.rejection_reason:
                    gov_stats["consecutive_losses"] += 1
                elif "EV" in dec.rejection_reason or "PF" in dec.rejection_reason:
                    gov_stats["rolling_perf"] += 1
                else:
                    gov_stats["drawdown_mode"] += 1
                continue
            plan = TradePlan(
                plan_id=f"RP-{uuid.uuid4().hex[:8].upper()}", symbol=candle.symbol,
                direction=direction, signal_time=candle.timestamp,
                entry_zone_high=entry + cr * 0.1, entry_zone_low=entry - cr * 0.1,
                stop_loss=stop, target_price=target,
            )
            trades = sim.process_candle(hc_to_lsm(candle), [plan])
            for t in trades:
                sel.record_outcome(getattr(t, "trade_id", rc2.candidate_id), t.net_r > 0, day_key)
                if t.net_r != 0.0:
                    gov.evaluate(t, grade=grade)

    daily_breakdown = defaultdict(int)
    for t in sim.completed_trades:
        ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
        if ts:
            daily_breakdown[ts.strftime("%Y-%m-%d")] += 1

    return compute_metrics(sim.completed_trades), ra, dict(daily_breakdown), gov_stats, regime_stats


def compute_metrics(trades: list) -> dict[str, Any]:
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "expectancy": 0, "profit_factor": 0, "avg_trades_per_day": 0, "max_drawdown": 0}
    wins = [t for t in trades if t.net_r > 0]
    losses = [t for t in trades if t.net_r <= 0]
    total_r = sum(t.net_r for t in trades)
    gross_profit = sum(t.net_r for t in wins)
    gross_loss = abs(sum(t.net_r for t in losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else 99.0
    day_set = set()
    for t in trades:
        ts = getattr(t, "signal_time", None) or getattr(t, "entry_time", None)
        if ts:
            day_set.add(ts.strftime("%Y-%m-%d"))
    num_days = max(len(day_set), 1)
    eq = [0]
    for t in trades:
        eq.append(eq[-1] + t.net_r)
    dd = 0
    peak = eq[0]
    for v in eq:
        if v > peak:
            peak = v
        dd = max(dd, peak - v)
    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "expectancy": total_r / len(trades) if trades else 0,
        "profit_factor": pf,
        "avg_trades_per_day": len(trades) / num_days,
        "max_drawdown": round(dd, 2),
    }


def hc_to_lsm(hc):
    return LsmCandle(symbol=hc.symbol, timeframe=hc.timeframe,
        timestamp=hc.timestamp, open=hc.open, high=hc.high,
        low=hc.low, close=hc.close, volume=hc.volume)


class _LsmPipeline:
    def __init__(self):
        from ultimate_trader.liquidity_smart_money import (
            SwingDetector, LiquidityPoolDetector, SweepDetector,
            MarketStructureEngine, FairValueGapDetector, OrderBlockDetector,
            PremiumDiscountEngine, DisplacementEngine, ConfluenceEngine,
        )
        self._sd = SwingDetector()
        self._ld = LiquidityPoolDetector()
        self._swd = SweepDetector()
        self._ms = MarketStructureEngine()
        self._fvg = FairValueGapDetector()
        self._ob = OrderBlockDetector()
        self._pd = PremiumDiscountEngine()
        self._disp = DisplacementEngine()
        self._cf = ConfluenceEngine()
        self._clist: list[LsmCandle] = []

    def process_candle(self, hc):
        lc = hc_to_lsm(hc)
        self._clist.append(lc)
        if len(self._clist) > 100:
            self._clist.pop(0)
        self._sd.add_candle(lc)
        sh = [s for s in self._sd._swing_points if str(s.swing_type) == "SwingType.SWING_HIGH"]
        sl = [s for s in self._sd._swing_points if str(s.swing_type) == "SwingType.SWING_LOW"]
        zones = self._ld.analyze(swing_highs=sh, swing_lows=sl, equal_highs=[], equal_lows=[], current_price=lc.close, candles=self._clist)
        sweeps = self._swd.analyze(candles=self._clist, liquidity_zones=zones)
        struct = self._ms.analyze(swing_highs=sh, swing_lows=sl, candles=self._clist)
        fvgs = self._fvg.analyze(self._clist)
        obs = self._ob.analyze(self._clist, fvgs)
        pds = self._pd.analyze(sh, sl, lc.close)
        dobj = self._disp.analyze(self._clist)
        disps = [dobj] if dobj else []
        conf = self._cf.analyze(liquidity_zones=zones, sweeps=sweeps, structure_events=struct, fvgs=fvgs, order_blocks=obs, premium_discount=pds, displacements=disps)
        is_long = str(conf.directional_bias) == "DirectionalBias.LONG"
        is_short = str(conf.directional_bias) == "DirectionalBias.SHORT"
        ds = "LONG" if is_long else ("SHORT" if is_short else "NEUTRAL")
        lsm_data = {
            "direction": ds, "confluence_score": conf.confluence_score,
            "trade_permission": str(conf.trade_permission),
            "swing_highs": sh, "swing_lows": sl, "sweeps": sweeps,
            "structure_events": struct, "fvgs": fvgs, "order_blocks": obs,
            "risk_score": 0.0,
            "sweep_bias": 1.0 if is_long else (-1.0 if is_short else 0.0),
            "structure_bias": 1.0 if is_long else (-1.0 if is_short else 0.0),
            "fvg_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "order_block_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "premium_discount_bias": -0.5 if is_long else (0.5 if is_short else 0.0),
            "displacement_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "microstructure_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "orderflow_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "trend_bias": 0.5 if is_long else (-0.5 if is_short else 0.0),
            "conflict_severity": "HIGH" if conf.conflict_score >= 0.6 else ("MEDIUM" if conf.conflict_score >= 0.3 else "NONE"),
        }
        return lsm_data, conf
