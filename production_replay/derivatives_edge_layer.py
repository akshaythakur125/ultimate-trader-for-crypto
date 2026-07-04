"""Derivatives Edge Layer for Phase 78.

Research layer using funding, open interest, volume expansion, and
price compression/trap logic. Uses cached OHLCV data. No historical
OI/funding is cached, so derivatives-aware setups are marked
LIVE_OBSERVATION_ONLY. Candle-confirmed parts are backtestable.

Setup types:
A. OI Build Compression (PRE_BREAKOUT_OBSERVE)
B. Funding Trap Reversal (LIVE_OBSERVATION_ONLY)
C. OI + Price Divergence (LIVE_OBSERVATION_ONLY)
D. Liquidation Proxy Sweep (BACKTESTABLE_EDGE)
E. Momentum Continuation After Squeeze (BACKTESTABLE_EDGE)

This module NEVER places real orders, NEVER enables live trading.
"""

import json, math, os, sys
from datetime import datetime, timezone
from statistics import mean, median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
CACHE_DIR = os.path.join(STATE_DIR, "candles_cache")
JSON_PATH = os.path.join(RESULTS_DIR, "derivatives_edge_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "derivatives_edge_report.txt")
CANDIDATES_PATH = os.path.join(STATE_DIR, "derivatives_edge_candidates.jsonl")

SPLIT_RATIO = 0.7
FEE_RATE = 0.0004
BANNED_FIELDS = {"r_result", "r_after_fees", "is_win", "outcome",
                 "exit_reason", "exit_price", "max_favorable_excursion_pct",
                 "max_adverse_excursion_pct", "holding_candles"}

# Backtest thresholds
MIN_TRADES = 300
MIN_OOS_TRADES = 100
MIN_OOS_AVG_R = 0.10
MIN_PROFIT_FACTOR = 1.15
MAX_CONSEC_LOSSES = 12


def _load_candles(symbol: str, timeframe: str) -> list[dict]:
    path = os.path.join(CACHE_DIR, f"{symbol}_{timeframe}.json")
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _get_symbols_for_timeframe(timeframe: str) -> list[str]:
    symbols = []
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith(f"_{timeframe}.json"):
                sym = f.replace(f"_{timeframe}.json", "")
                symbols.append(sym)
    return sorted(symbols)


def _ema(data: list[float], period: int) -> float:
    if len(data) < period:
        return mean(data) if data else 0
    k = 2 / (period + 1)
    ema_val = mean(data[:period])
    for val in data[period:]:
        ema_val = val * k + ema_val * (1 - k)
    return ema_val


def _avg_range(candles: list[dict], idx: int, lookback: int) -> float:
    if idx < lookback:
        return 0
    ranges = [float(candles[j].get("high", 0)) - float(candles[j].get("low", 0))
              for j in range(idx - lookback, idx)]
    return mean(ranges) if ranges else 0


def _avg_volume(candles: list[dict], idx: int, lookback: int) -> float:
    if idx < lookback:
        return 0
    vols = [float(candles[j].get("volume", 0)) for j in range(idx - lookback, idx)]
    return mean(vols) if vols else 0


def _simulate_trade(candles: list[dict], entry_idx: int, direction: str,
                    entry: float, stop: float, target: float,
                    max_holding: int = 48) -> dict:
    risk = abs(entry - stop)
    if risk <= 0:
        return {"r_result": 0, "outcome": "INVALID", "exit_idx": entry_idx, "exit_price": entry, "holding": 0}
    for i in range(entry_idx + 1, min(entry_idx + max_holding + 1, len(candles))):
        c = candles[i]
        high = float(c.get("high", 0))
        low = float(c.get("low", 0))
        if direction == "LONG":
            if low <= stop:
                return {"r_result": -1.0, "outcome": "STOP_HIT", "exit_idx": i, "exit_price": stop, "holding": i - entry_idx}
            if high >= target:
                return {"r_result": round((target - entry) / risk, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}
        else:
            if high >= stop:
                return {"r_result": -1.0, "outcome": "STOP_HIT", "exit_idx": i, "exit_price": stop, "holding": i - entry_idx}
            if low <= target:
                return {"r_result": round((entry - target) / risk, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}
    last_idx = min(entry_idx + max_holding, len(candles) - 1)
    close = float(candles[last_idx].get("close", entry))
    r = ((close - entry) / risk) if direction == "LONG" else ((entry - close) / risk)
    return {"r_result": round(r, 4), "outcome": "EXPIRED", "exit_idx": last_idx, "exit_price": close, "holding": last_idx - entry_idx}


# --- SETUP DETECTORS ---

def detect_oi_build_compression(candles: list[dict], i: int) -> dict | None:
    """OI Build Compression: price range small, volume rising, no breakout yet.
    Marked PRE_BREAKOUT_OBSERVE (no entry, just candidate).
    """
    if i < 20:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    cl = float(c.get("close", 0))
    op = float(c.get("open", 0))
    vol = float(c.get("volume", 0))
    rng = high - low
    avg_rng = _avg_range(candles, i, 20)
    avg_vol = _avg_volume(candles, i, 20)
    if avg_rng <= 0 or avg_vol <= 0:
        return None
    is_compressed = rng < 0.5 * avg_rng
    vol_expanding = vol > avg_vol * 1.2
    recent_vol_trend = [_avg_volume(candles, j, 5) for j in range(i - 5, i)]
    vol_rising = all(recent_vol_trend[j] <= recent_vol_trend[j + 1] for j in range(len(recent_vol_trend) - 1)) if len(recent_vol_trend) > 1 else False
    if is_compressed and vol_expanding:
        compression_score = round(1 - (rng / avg_rng), 2)
        confidence = round((compression_score * 0.5 + (vol / avg_vol - 1) * 0.5), 2)
        return {
            "setup_type": "OI_BUILD_COMPRESSION",
            "category": "PRE_BREAKOUT_OBSERVE",
            "direction": "NEUTRAL",
            "entry": cl,
            "stop": 0,
            "target": 0,
            "rr": 0,
            "compression_score": compression_score,
            "volume_expansion": round(vol / avg_vol, 2),
            "trap_score": 0,
            "confidence": min(confidence, 1.0),
            "funding_status": "NO_DATA",
            "oi_status": "NO_DATA",
            "reason": f"compressed range {compression_score:.0%}, volume {vol/avg_vol:.1f}x avg",
        }
    return None


def detect_funding_trap_reversal(candles: list[dict], i: int) -> dict | None:
    """Funding Trap Reversal: price fails to continue after momentum.
    Uses candle patterns as proxy (no real funding data).
    Marked LIVE_OBSERVATION_ONLY.
    """
    if i < 20:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    body = abs(cl - op)
    rng = high - low
    if body <= 0 or rng <= 0:
        return None
    recent_closes = [float(candles[j].get("close", 0)) for j in range(i - 10, i)]
    if not recent_closes or recent_closes[0] <= 0:
        return None
    momentum = (cl - recent_closes[0]) / recent_closes[0]
    lower_wick = min(op, cl) - low
    upper_wick = high - max(op, cl)
    if momentum > 0.015 and upper_wick > 1.5 * body and cl < op:
        risk = abs(high * 1.002 - cl)
        if risk / cl > 0.001:
            return {
                "setup_type": "FUNDING_TRAP_REVERSAL",
                "category": "LIVE_OBSERVATION_ONLY",
                "direction": "SHORT",
                "entry": cl,
                "stop": high * 1.002,
                "target": cl - risk * 3.0,
                "rr": 3.0,
                "compression_score": 0,
                "volume_expansion": 0,
                "trap_score": round(min(abs(momentum) * 10, 1.0), 2),
                "confidence": round(min(abs(momentum) * 5, 1.0), 2),
                "funding_status": "PROXY_ONLY",
                "oi_status": "NO_DATA",
                "reason": f"up-momentum {momentum:.3f} failed with upper wick rejection",
            }
    if momentum < -0.015 and lower_wick > 1.5 * body and cl > op:
        risk = abs(cl - low * 0.998)
        if risk / cl > 0.001:
            return {
                "setup_type": "FUNDING_TRAP_REVERSAL",
                "category": "LIVE_OBSERVATION_ONLY",
                "direction": "LONG",
                "entry": cl,
                "stop": low * 0.998,
                "target": cl + risk * 3.0,
                "rr": 3.0,
                "compression_score": 0,
                "volume_expansion": 0,
                "trap_score": round(min(abs(momentum) * 10, 1.0), 2),
                "confidence": round(min(abs(momentum) * 5, 1.0), 2),
                "funding_status": "PROXY_ONLY",
                "oi_status": "NO_DATA",
                "reason": f"down-momentum {momentum:.3f} failed with lower wick rejection",
            }
    return None


def detect_oi_price_divergence(candles: list[dict], i: int) -> dict | None:
    """OI + Price Divergence: OI rising while price flat.
    Uses volume as OI proxy (no real OI data).
    Marked LIVE_OBSERVATION_ONLY.
    """
    if i < 20:
        return None
    c = candles[i]
    cl = float(c.get("close", 0))
    vol = float(c.get("volume", 0))
    avg_vol = _avg_volume(candles, i, 20)
    if avg_vol <= 0:
        return None
    closes = [float(candles[j].get("close", 0)) for j in range(i - 10, i)]
    if not closes or closes[0] <= 0:
        return None
    price_change = abs(cl - closes[0]) / closes[0]
    vol_ratio = vol / avg_vol
    is_flat = price_change < 0.005
    vol_rising = vol_ratio > 1.3
    if is_flat and vol_rising:
        closes_20 = [float(candles[j].get("close", 0)) for j in range(i - 20, i)]
        ema20 = _ema(closes_20, 20)
        direction = "LONG" if cl > ema20 else "SHORT"
        risk = abs(cl * 0.01)
        if direction == "LONG":
            return {
                "setup_type": "OI_PRICE_DIVERGENCE",
                "category": "LIVE_OBSERVATION_ONLY",
                "direction": direction,
                "entry": cl,
                "stop": cl - risk,
                "target": cl + risk * 2.5,
                "rr": 2.5,
                "compression_score": 0,
                "volume_expansion": round(vol_ratio, 2),
                "trap_score": 0,
                "confidence": round(min((vol_ratio - 1) * 0.5, 1.0), 2),
                "funding_status": "NO_DATA",
                "oi_status": "PROXY_ONLY",
                "reason": f"flat price {price_change:.3%} with volume {vol_ratio:.1f}x",
            }
        else:
            return {
                "setup_type": "OI_PRICE_DIVERGENCE",
                "category": "LIVE_OBSERVATION_ONLY",
                "direction": direction,
                "entry": cl,
                "stop": cl + risk,
                "target": cl - risk * 2.5,
                "rr": 2.5,
                "compression_score": 0,
                "volume_expansion": round(vol_ratio, 2),
                "trap_score": 0,
                "confidence": round(min((vol_ratio - 1) * 0.5, 1.0), 2),
                "funding_status": "NO_DATA",
                "oi_status": "PROXY_ONLY",
                "reason": f"flat price {price_change:.3%} with volume {vol_ratio:.1f}x",
            }
    return None


def detect_liquidation_proxy_sweep(candles: list[dict], i: int,
                                   lookback: int = 20, rr_target: float = 3.0) -> dict | None:
    """Liquidation Proxy Sweep: equal highs/lows, sweep, close back inside.
    Backtestable using candle data only.
    """
    if i < lookback + 2:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    vol = float(c.get("volume", 0))
    body = abs(cl - op)
    avg_vol = _avg_volume(candles, i, 20)
    if body <= 0:
        return None
    recent_highs = [float(candles[j].get("high", 0)) for j in range(i - lookback, i)]
    recent_lows = [float(candles[j].get("low", 0)) for j in range(i - lookback, i)]
    max_high = max(recent_highs) if recent_highs else 0
    min_low = min(recent_lows) if recent_lows else 0
    high_cluster = sum(1 for h in recent_highs if abs(h - max_high) / max_high < 0.002 if max_high > 0)
    low_cluster = sum(1 for l in recent_lows if abs(l - min_low) / min_low < 0.002 if min_low > 0)
    if low < min_low and cl > op and cl > min_low and low_cluster >= 3:
        lower_wick = min(op, cl) - low
        if lower_wick >= 0.8 * body and (avg_vol <= 0 or vol > avg_vol):
            risk = abs(cl - min_low * 0.998)
            if risk / cl > 0.001:
                return {
                    "setup_type": "LIQUIDATION_PROXY_SWEEP",
                    "category": "BACKTESTABLE_EDGE",
                    "direction": "LONG",
                    "entry": cl,
                    "stop": min_low * 0.998,
                    "target": cl + risk * rr_target,
                    "rr": rr_target,
                    "compression_score": 0,
                    "volume_expansion": round(vol / avg_vol, 2) if avg_vol > 0 else 0,
                    "trap_score": round(high_cluster / lookback, 2),
                    "confidence": round(min(lower_wick / body * 0.3 + (vol / avg_vol - 1) * 0.3 if avg_vol > 0 else 0.5, 1.0), 2),
                    "funding_status": "NO_DATA",
                    "oi_status": "NO_DATA",
                    "reason": f"swept {low_cluster} lows, closed back inside, wick {lower_wick/body:.1f}x body",
                }
    if high > max_high and cl < op and cl < max_high and high_cluster >= 3:
        upper_wick = high - max(op, cl)
        if upper_wick >= 0.8 * body and (avg_vol <= 0 or vol > avg_vol):
            risk = abs(max_high * 1.002 - cl)
            if risk / cl > 0.001:
                return {
                    "setup_type": "LIQUIDATION_PROXY_SWEEP",
                    "category": "BACKTESTABLE_EDGE",
                    "direction": "SHORT",
                    "entry": cl,
                    "stop": max_high * 1.002,
                    "target": cl - risk * rr_target,
                    "rr": rr_target,
                    "compression_score": 0,
                    "volume_expansion": round(vol / avg_vol, 2) if avg_vol > 0 else 0,
                    "trap_score": round(high_cluster / lookback, 2),
                    "confidence": round(min(upper_wick / body * 0.3 + (vol / avg_vol - 1) * 0.3 if avg_vol > 0 else 0.5, 1.0), 2),
                    "funding_status": "NO_DATA",
                    "oi_status": "NO_DATA",
                    "reason": f"swept {high_cluster} highs, closed back inside, wick {upper_wick/body:.1f}x body",
                }
    return None


def detect_momentum_continuation_squeeze(candles: list[dict], i: int,
                                         rr_target: float = 3.0) -> dict | None:
    """Momentum Continuation After Squeeze: compression -> breakout -> retest.
    Backtestable using candle data only.
    """
    if i < 30:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    rng = high - low
    body = abs(cl - op)
    if body <= 0 or rng <= 0:
        return None
    avg_rng = _avg_range(candles, i, 20)
    if avg_rng <= 0:
        return None
    is_compressed = all(
        (float(candles[j].get("high", 0)) - float(candles[j].get("low", 0))) < 0.6 * avg_rng
        for j in range(i - 3, i)
    )
    if not is_compressed:
        return None
    breakout_up = cl > op and rng > 1.3 * avg_rng and cl > max(float(candles[j].get("high", 0)) for j in range(i - 5, i))
    breakout_down = cl < op and rng > 1.3 * avg_rng and cl < min(float(candles[j].get("low", 0)) for j in range(i - 5, i))
    if i < 3:
        return None
    prev_close = float(candles[i - 1].get("close", 0))
    if breakout_up and cl > prev_close:
        risk = abs(cl - max(float(candles[j].get("high", 0)) for j in range(i - 5, i)) * 0.998)
        if risk / cl > 0.001:
            return {
                "setup_type": "MOMENTUM_CONTINUATION_SQUEEZE",
                "category": "BACKTESTABLE_EDGE",
                "direction": "LONG",
                "entry": cl,
                "stop": max(float(candles[j].get("high", 0)) for j in range(i - 5, i)) * 0.998,
                "target": cl + risk * rr_target,
                "rr": rr_target,
                "compression_score": round(1 - (rng / avg_rng), 2),
                "volume_expansion": 0,
                "trap_score": 0,
                "confidence": round(min((1 - rng / avg_rng) * 0.5 + rng / avg_rng * 0.5, 1.0), 2),
                "funding_status": "NO_DATA",
                "oi_status": "NO_DATA",
                "reason": f"compressed {3} candles, breakout up, retest hold",
            }
    if breakout_down and cl < prev_close:
        risk = abs(min(float(candles[j].get("low", 0)) for j in range(i - 5, i)) * 1.002 - cl)
        if risk / cl > 0.001:
            return {
                "setup_type": "MOMENTUM_CONTINUATION_SQUEEZE",
                "category": "BACKTESTABLE_EDGE",
                "direction": "SHORT",
                "entry": cl,
                "stop": min(float(candles[j].get("low", 0)) for j in range(i - 5, i)) * 1.002,
                "target": cl - risk * rr_target,
                "rr": rr_target,
                "compression_score": round(1 - (rng / avg_rng), 2),
                "volume_expansion": 0,
                "trap_score": 0,
                "confidence": round(min((1 - rng / avg_rng) * 0.5 + rng / avg_rng * 0.5, 1.0), 2),
                "funding_status": "NO_DATA",
                "oi_status": "NO_DATA",
                "reason": f"compressed {3} candles, breakout down, retest hold",
            }
    return None


# --- STATS AND PROMOTION ---

def _net_r(t: dict) -> float:
    """R after fees; falls back to gross r_result for trades without fee data."""
    return t.get("r_after_fees", t.get("r_result", 0))


def _max_dd(trades: list[dict]) -> float:
    peak = 0
    dd = 0
    equity = 0
    for t in trades:
        equity += _net_r(t)
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return round(dd, 2)


def _max_consec(trades: list[dict]) -> int:
    max_c = 0
    curr = 0
    for t in trades:
        if _net_r(t) <= 0:
            curr += 1
            max_c = max(max_c, curr)
        else:
            curr = 0
    return max_c


def _compute_stats(trades: list[dict]) -> dict:
    """All stats are net of fees so promotion gates reflect tradable results."""
    if not trades:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_r": 0.0,
                "total_r": 0.0, "max_dd": 0.0, "max_consec": 0, "profit_factor": 0.0,
                "symbols": set()}
    trades = sorted(trades, key=lambda t: t.get("entry_time", 0))
    r_vals = [_net_r(t) for t in trades]
    wins = [r for r in r_vals if r > 0]
    losses = [r for r in r_vals if r <= 0]
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else float("inf")
    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_r": round(mean(r_vals), 4),
        "total_r": round(sum(r_vals), 2),
        "max_dd": _max_dd(trades),
        "max_consec": _max_consec(trades),
        "profit_factor": round(pf, 4),
        "symbols": {t["symbol"] for t in trades},
    }


def _check_promotion(stats: dict, is_stats: dict, oos_stats: dict) -> tuple[str, list[str]]:
    reasons = []
    reject = False
    if stats["trades"] < MIN_TRADES:
        reasons.append(f"total trades {stats['trades']} < {MIN_TRADES}")
        reject = True
    if oos_stats["trades"] < MIN_OOS_TRADES:
        reasons.append(f"OOS trades {oos_stats['trades']} < {MIN_OOS_TRADES}")
        reject = True
    if len(stats["symbols"]) < 50:
        reasons.append(f"symbols {len(stats['symbols'])} < 50")
        reject = True
    if oos_stats["avg_r"] <= MIN_OOS_AVG_R:
        reasons.append(f"OOS avg R {oos_stats['avg_r']} <= {MIN_OOS_AVG_R}")
        reject = True
    if stats["profit_factor"] <= MIN_PROFIT_FACTOR:
        reasons.append(f"PF {stats['profit_factor']} <= {MIN_PROFIT_FACTOR}")
        reject = True
    if stats["max_consec"] > MAX_CONSEC_LOSSES:
        reasons.append(f"max consec {stats['max_consec']} > {MAX_CONSEC_LOSSES}")
        reject = True
    if is_stats["avg_r"] > 0 and oos_stats["avg_r"] <= 0:
        reasons.append("overfit: IS positive but OOS negative")
        reject = True
    if reject:
        return ("OBSERVE_ONLY" if len(reasons) <= 2 else "REJECTED"), reasons
    if (oos_stats["avg_r"] >= MIN_OOS_AVG_R and stats["profit_factor"] >= MIN_PROFIT_FACTOR):
        return "PAPER_PRIORITY", reasons
    return "PAPER_CANDIDATE", reasons


# --- MAIN DERIVATIVES EDGE RUNNER ---

SETUP_DETECTORS = [
    ("LIQUIDATION_PROXY_SWEEP", detect_liquidation_proxy_sweep),
    ("MOMENTUM_CONTINUATION_SQUEEZE", detect_momentum_continuation_squeeze),
    ("OI_BUILD_COMPRESSION", detect_oi_build_compression),
    ("FUNDING_TRAP_REVERSAL", detect_funding_trap_reversal),
    ("OI_PRICE_DIVERGENCE", detect_oi_price_divergence),
]


def _run_backtestable_detector(name: str, detector, symbols: list[str],
                                timeframe: str, rr_target: float = 3.0) -> dict | None:
    all_trades = []
    seen_keys = set()
    for sym in symbols:
        candles = _load_candles(sym, timeframe)
        if len(candles) < 60:
            continue
        open_until = -1  # no overlapping trades on the same symbol
        for i in range(30, len(candles) - 1):
            if i <= open_until:
                continue
            sig = detector(candles, i)
            if sig is None:
                continue
            if sig.get("category") != "BACKTESTABLE_EDGE":
                continue
            direction = sig["direction"]
            entry = sig["entry"]
            stop = sig["stop"]
            target = sig["target"]
            sig_key = f"{sym}_{timeframe}_{direction}_{i}"
            if sig_key in seen_keys:
                continue
            seen_keys.add(sig_key)
            result = _simulate_trade(candles, i, direction, entry, stop, target, 48)
            open_until = result["exit_idx"]
            fee = (entry + result["exit_price"]) * FEE_RATE
            r_after_fees = result["r_result"] - fee / abs(entry - stop) if abs(entry - stop) > 0 else result["r_result"]
            trade = {
                "symbol": sym, "timeframe": timeframe, "direction": direction,
                "pattern": sig["setup_type"], "entry_price": entry, "stop": stop,
                "target": target, "exit_price": result["exit_price"],
                "entry_time": int(candles[i].get("timestamp", i)),
                "r_result": result["r_result"], "r_after_fees": round(r_after_fees, 4),
                "is_win": result["r_result"] > 0,
            }
            all_trades.append(trade)
    if not all_trades:
        return None
    # Walk-forward split: 70/30 by entry time, so OOS is strictly later in time
    sorted_t = sorted(all_trades, key=lambda t: t.get("entry_time", 0))
    split = int(len(sorted_t) * SPLIT_RATIO)
    is_t = sorted_t[:split]
    oos_t = sorted_t[split:]
    all_stats = _compute_stats(all_trades)
    is_stats = _compute_stats(is_t)
    oos_stats = _compute_stats(oos_t)
    verdict, reasons = _check_promotion(all_stats, is_stats, oos_stats)
    return {
        "setup_type": name, "timeframe": timeframe, "rr_target": rr_target,
        "total_trades": all_stats["trades"], "oos_trades": oos_stats["trades"],
        "win_rate": all_stats["win_rate"], "avg_r": all_stats["avg_r"],
        "is_avg_r": is_stats["avg_r"], "oos_avg_r": oos_stats["avg_r"],
        "oos_win_rate": oos_stats["win_rate"],
        "profit_factor": all_stats["profit_factor"],
        "max_dd": all_stats["max_dd"], "max_consec": all_stats["max_consec"],
        "unique_symbols": len(all_stats["symbols"]),
        "verdict": verdict, "reject_reasons": reasons,
    }


def run_derivatives_edge_layer() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    backtestable_results = []
    live_observation_candidates = []
    timeframes = ["15m", "30m"]
    for name, detector in SETUP_DETECTORS:
        for tf in timeframes:
            symbols = _get_symbols_for_timeframe(tf)
            if not symbols:
                continue
            result = _run_backtestable_detector(name, detector, symbols, tf)
            if result is not None:
                backtestable_results.append(result)
    live_oi_compression = 0
    live_funding_trap = 0
    live_oi_divergence = 0
    for tf in timeframes:
        symbols = _get_symbols_for_timeframe(tf)
        for sym in symbols[:20]:
            candles = _load_candles(sym, tf)
            if len(candles) < 60:
                continue
            for i in range(30, len(candles)):
                sig = detect_oi_build_compression(candles, i)
                if sig:
                    live_oi_compression += 1
                    live_observation_candidates.append({**sig, "symbol": sym, "timeframe": tf})
                    break
                sig = detect_funding_trap_reversal(candles, i)
                if sig:
                    live_funding_trap += 1
                    live_observation_candidates.append({**sig, "symbol": sym, "timeframe": tf})
                    break
                sig = detect_oi_price_divergence(candles, i)
                if sig:
                    live_oi_divergence += 1
                    live_observation_candidates.append({**sig, "symbol": sym, "timeframe": tf})
                    break
    best_backtest = None
    for r in backtestable_results:
        if r["verdict"] in ("PAPER_CANDIDATE", "PAPER_PRIORITY"):
            if best_backtest is None or r["oos_avg_r"] > best_backtest.get("oos_avg_r", 0):
                best_backtest = r
    if best_backtest and best_backtest.get("verdict") == "PAPER_PRIORITY":
        final_decision = "PAPER_PRIORITY_FOUND"
    elif best_backtest and best_backtest.get("verdict") == "PAPER_CANDIDATE":
        final_decision = "BACKTESTABLE_EDGE_FOUND"
    elif live_observation_candidates:
        final_decision = "PAPER_WATCHLIST_ONLY"
    else:
        final_decision = "NO_EDGE_FOUND"
    with open(CANDIDATES_PATH, "w") as f:
        for c in live_observation_candidates:
            f.write(json.dumps(c) + "\n")
        for r in backtestable_results:
            if r["verdict"] in ("PAPER_CANDIDATE", "PAPER_PRIORITY"):
                f.write(json.dumps(r) + "\n")
    report = {
        "mode": "derivatives_edge_layer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "real_order": False,
        "final_decision": final_decision,
        "backtestable_results": backtestable_results,
        "best_backtest": best_backtest,
        "live_observation": {
            "oi_compression_count": live_oi_compression,
            "funding_trap_count": live_funding_trap,
            "oi_divergence_count": live_oi_divergence,
            "total_candidates": len(live_observation_candidates),
            "note": "No historical OI/funding cached. These are candle-pattern proxies only.",
        },
        "warnings": ["No historical OI or funding data cached. Derivatives-aware setups use candle-pattern proxies."],
    }
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    _write_text_report(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  DERIVATIVES EDGE LAYER",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Final Decision:     {report['final_decision']}",
        f"  Live Trading:       NO",
        "",
    ]
    best = report.get("best_backtest")
    if best:
        lines += [
            "  BEST BACKTESTABLE EDGE:",
            f"    Setup:        {best['setup_type']}",
            f"    Timeframe:    {best['timeframe']}",
            f"    Total Trades: {best['total_trades']}",
            f"    OOS Trades:   {best['oos_trades']}",
            f"    OOS Avg R:    {best['oos_avg_r']}",
            f"    Profit Factor:{best['profit_factor']}",
            f"    Max DD:       {best['max_dd']}",
            f"    Verdict:      {best['verdict']}",
            "",
        ]
    else:
        lines += ["  BEST BACKTESTABLE EDGE: NONE", ""]
    bt = report.get("backtestable_results", [])
    if bt:
        lines += [f"  BACKTESTABLE RESULTS ({len(bt)}):", ""]
        for r in sorted(bt, key=lambda x: -x.get("oos_avg_r", 0)):
            lines.append(
                f"    {r['setup_type'][:25]:25s} {r['timeframe']:4s} "
                f"OOS_R:{r['oos_avg_r']:.3f} PF:{r['profit_factor']:.2f} "
                f"Trades:{r['total_trades']} {r['verdict']}"
            )
    lo = report.get("live_observation", {})
    lines += [
        "",
        "  LIVE OBSERVATION ONLY:",
        f"    OI Compression:    {lo.get('oi_compression_count', 0)}",
        f"    Funding Trap:      {lo.get('funding_trap_count', 0)}",
        f"    OI Divergence:     {lo.get('oi_divergence_count', 0)}",
        f"    Total Candidates:  {lo.get('total_candidates', 0)}",
        f"    Note:              {lo.get('note', '')}",
        "",
        "  WARNING: No real orders placed. Paper/backtest only.",
        "",
        "=" * 60,
    ]
    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    print(f"[CANDIDATES] {CANDIDATES_PATH}")


def main():
    report = run_derivatives_edge_layer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
