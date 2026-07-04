"""Breadwinner Strategy Library — Liquidity Sweep Reversal v2.

A focused strategy model inspired by proven public trading concepts:
liquidity sweep reversal + mean reversion confirmation.

Strategy: LIQUIDITY_SWEEP_REVERSAL_V2

Long setup:
- price sweeps previous swing low / recent liquidity low
- candle closes back above swept level
- wick rejection present
- volume above recent average
- entry after reclaim confirmation, not at wick extreme
- stop below sweep low
- target minimum RR 2.5, also test RR 3 and RR 4

Short setup:
- price sweeps previous swing high / recent liquidity high
- candle closes back below swept level
- wick rejection present
- volume above recent average
- entry after reclaim rejection confirmation
- stop above sweep high
- target minimum RR 2.5, also test RR 3 and RR 4

Filters:
- 15m and 30m only
- only coins with enough history
- reject setups with bad spread/liquidity proxy
- max holding time: 12 to 48 candles
- no overlapping trades on same symbol
- walk-forward split: 70% in-sample, 30% out-of-sample
- no outcome leakage
- no future data in entry logic

This module NEVER places real orders, NEVER enables live trading.
"""

import json, math, os, sys
from datetime import datetime, timezone
from statistics import mean, median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
CACHE_DIR = os.path.join(STATE_DIR, "candles_cache")
JSON_PATH = os.path.join(RESULTS_DIR, "breadwinner_strategy_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "breadwinner_strategy_report.txt")

# Strategy parameters
TIMEFRAMES = ["15m", "30m"]
RR_TARGETS = [2.5, 3.0, 4.0]
SWEEP_LOOKBACK = 20
VOLUME_LOOKBACK = 20
MAX_HOLDING = 48
MIN_RISK_PCT = 0.001  # 0.1% minimum risk
FEE_RATE = 0.0004  # 0.04% per side
SPLIT_RATIO = 0.7  # 70/30 walk-forward

# Promotion thresholds (stricter than general edge miner)
MIN_TRADES = 300
MIN_OOS_TRADES = 100
MIN_SYMBOLS = 50
MIN_OOS_AVG_R = 0.15
MIN_OOS_WIN_RATE = 35.0
MIN_PROFIT_FACTOR = 1.2
MAX_MAX_DD = 200.0
MAX_CONSEC_LOSSES = 12

# Outcome-derived fields that must NOT be used
BANNED_FIELDS = {"r_result", "r_after_fees", "is_win", "outcome",
                 "exit_reason", "exit_price", "max_favorable_excursion_pct",
                 "max_adverse_excursion_pct", "holding_candles"}


def _load_candles(symbol: str, timeframe: str) -> list[dict]:
    path = os.path.join(CACHE_DIR, f"{symbol}_{timeframe}.json")
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


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


def _sma(closes: list[float], period: int) -> float:
    if len(closes) < period:
        return 0
    return sum(closes[-period:]) / period


def _find_swing_low(candles: list[dict], idx: int, lookback: int) -> float:
    if idx < lookback:
        return float("inf")
    lows = [float(candles[j].get("low", 0)) for j in range(idx - lookback, idx)]
    return min(lows) if lows else float("inf")


def _find_swing_high(candles: list[dict], idx: int, lookback: int) -> float:
    if idx < lookback:
        return 0
    highs = [float(candles[j].get("high", 0)) for j in range(idx - lookback, idx)]
    return max(highs) if highs else 0


def detect_liquidity_sweep_v2(
    candles: list[dict],
    idx: int,
    sweep_lookback: int = SWEEP_LOOKBACK,
    volume_lookback: int = VOLUME_LOOKBACK,
    max_holding: int = MAX_HOLDING,
    rr_target: float = 3.0,
) -> dict | None:
    """Detect Liquidity Sweep Reversal v2 setup.

    Returns dict with direction, entry, stop, target, pattern, filters, or None.
    No future data used. Only candle data up to idx is used.
    """
    if idx < sweep_lookback + 5:
        return None

    c = candles[idx]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    vol = float(c.get("volume", 0))
    body = abs(cl - op)
    rng = high - low

    if body <= 0 or rng <= 0:
        return None

    # Volume filter: must be above average
    avg_vol = _avg_volume(candles, idx, volume_lookback)
    if avg_vol <= 0 or vol < avg_vol * 1.0:
        return None

    # Range filter: reject abnormally huge candles (>3x average range)
    avg_rng = _avg_range(candles, idx, sweep_lookback)
    if avg_rng <= 0 or rng > avg_rng * 3.0:
        return None

    # Liquidity proxy: reject if spread is too wide (>1% of price)
    spread_proxy = rng / cl if cl > 0 else 0
    if spread_proxy > 0.01:
        return None

    swing_low = _find_swing_low(candles, idx, sweep_lookback)
    swing_high = _find_swing_high(candles, idx, sweep_lookback)

    # LONG setup: swept below swing low, closed back above
    if low < swing_low and cl > op and cl > low * 1.002:
        lower_wick = min(op, cl) - low
        if lower_wick >= 1.0 * body:
            risk = abs(cl - low * 0.998)
            if risk / cl > MIN_RISK_PCT:
                target = cl + risk * rr_target
                return {
                    "direction": "LONG",
                    "entry": cl,
                    "stop": low * 0.998,
                    "target": target,
                    "pattern": "liquidity_sweep_reversal_v2",
                    "swing_level": swing_low,
                    "wick_ratio": lower_wick / body,
                    "volume_ratio": vol / avg_vol if avg_vol > 0 else 0,
                    "range_ratio": rng / avg_rng if avg_rng > 0 else 0,
                    "max_holding": max_holding,
                }

    # SHORT setup: swept above swing high, closed back below
    if high > swing_high and cl < op and cl < high * 0.998:
        upper_wick = high - max(op, cl)
        if upper_wick >= 1.0 * body:
            risk = abs(high * 1.002 - cl)
            if risk / cl > MIN_RISK_PCT:
                target = cl - risk * rr_target
                return {
                    "direction": "SHORT",
                    "entry": cl,
                    "stop": high * 1.002,
                    "target": target,
                    "pattern": "liquidity_sweep_reversal_v2",
                    "swing_level": swing_high,
                    "wick_ratio": upper_wick / body,
                    "volume_ratio": vol / avg_vol if avg_vol > 0 else 0,
                    "range_ratio": rng / avg_rng if avg_rng > 0 else 0,
                    "max_holding": max_holding,
                }

    return None


def _bollinger_bands(closes: list[float], period: int, std_mult: float) -> tuple[float, float, float]:
    """Compute Bollinger Bands. Returns (lower, mid, upper)."""
    if len(closes) < period:
        return (0, 0, 0)
    recent = closes[-period:]
    mid = sum(recent) / period
    var = sum((x - mid) ** 2 for x in recent) / period
    sd = math.sqrt(var)
    lower = mid - std_mult * sd
    upper = mid + std_mult * sd
    return (lower, mid, upper)


def detect_bb_bounce(
    candles: list[dict],
    idx: int,
    period: int = 15,
    std_mult: float = 3.5,
    rr_target: float = 10.0,
    max_holding: int = 0,
) -> dict | None:
    """Detect Bollinger Band bounce setup.

    LONG: close below lower band (mean reversion)
    SHORT: close above upper band (mean reversion)
    Stop: 0.5% of entry, Target: entry +/- stop*rr_target
    No max holding — trades run until stop or target.
    """
    if idx < period + 5:
        return None

    c = candles[idx]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    cl = float(c.get("close", 0))
    body = abs(cl - float(c.get("open", 0)))
    rng = high - low

    if body <= 0 or rng <= 0:
        return None

    closes = [float(cc.get("close", 0)) for cc in candles[:idx + 1]]
    lower, mid, upper = _bollinger_bands(closes, period, std_mult)

    if cl <= lower:
        if idx + 1 >= len(candles):
            return None
        entry = float(candles[idx + 1].get("open", 0))
        if entry <= 0:
            return None
        risk_pct = 0.005
        stop_px = entry * (1 - risk_pct)
        target_px = entry * (1 + risk_pct * rr_target)
        return {
            "direction": "LONG",
            "entry": entry,
            "stop": stop_px,
            "target": target_px,
            "pattern": "bb_bounce_v1",
            "bb_lower": lower,
            "bb_mid": mid,
            "bb_upper": upper,
            "lookback": period,
            "std_mult": std_mult,
            "max_holding": max_holding,
        }

    if cl >= upper:
        if idx + 1 >= len(candles):
            return None
        entry = float(candles[idx + 1].get("open", 0))
        if entry <= 0:
            return None
        risk_pct = 0.005
        stop_px = entry * (1 + risk_pct)
        target_px = entry * (1 - risk_pct * rr_target)
        return {
            "direction": "SHORT",
            "entry": entry,
            "stop": stop_px,
            "target": target_px,
            "pattern": "bb_bounce_v1",
            "bb_lower": lower,
            "bb_mid": mid,
            "bb_upper": upper,
            "lookback": period,
            "std_mult": std_mult,
            "max_holding": max_holding,
        }

    return None


def simulate_trade(
    candles: list[dict],
    entry_idx: int,
    direction: str,
    entry: float,
    stop: float,
    target: float,
    max_holding: int = MAX_HOLDING,
) -> dict:
    """Simulate a trade forward from entry_idx. Returns R-multiple and outcome."""
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
                r = (target - entry) / risk
                return {"r_result": round(r, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}
        else:
            if high >= stop:
                return {"r_result": -1.0, "outcome": "STOP_HIT", "exit_idx": i, "exit_price": stop, "holding": i - entry_idx}
            if low <= target:
                r = (entry - target) / risk
                return {"r_result": round(r, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}

    last_idx = min(entry_idx + max_holding, len(candles) - 1)
    close = float(candles[last_idx].get("close", entry))
    if direction == "LONG":
        r = (close - entry) / risk
    else:
        r = (entry - close) / risk
    return {"r_result": round(r, 4), "outcome": "EXPIRED", "exit_idx": last_idx, "exit_price": close, "holding": last_idx - entry_idx}


def _max_dd(trades: list[dict]) -> float:
    peak = 0
    dd = 0
    equity = 0
    for t in trades:
        equity += t.get("r_result", 0)
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return round(dd, 2)


def _max_consec(trades: list[dict]) -> int:
    max_c = 0
    curr = 0
    for t in trades:
        if t.get("r_result", 0) <= 0:
            curr += 1
            max_c = max(max_c, curr)
        else:
            curr = 0
    return max_c


def _compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_r": 0.0,
                "total_r": 0.0, "max_dd": 0.0, "max_consec": 0, "profit_factor": 0.0,
                "symbols": set(), "timeframes": set()}
    r_vals = [t["r_result"] for t in trades]
    wins = [t for t in trades if t["r_result"] > 0]
    losses = [t for t in trades if t["r_result"] <= 0]
    gw = sum(t["r_result"] for t in wins)
    gl = abs(sum(t["r_result"] for t in losses))
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
        "timeframes": {t["timeframe"] for t in trades},
    }


def _check_promotion(stats: dict, is_stats: dict, oos_stats: dict) -> tuple[str, list[str]]:
    """Check if strategy meets promotion criteria. Returns (verdict, reasons)."""
    reasons = []
    reject = False

    if stats["trades"] < MIN_TRADES:
        reasons.append(f"total trades {stats['trades']} < {MIN_TRADES}")
        reject = True
    if oos_stats["trades"] < MIN_OOS_TRADES:
        reasons.append(f"OOS trades {oos_stats['trades']} < {MIN_OOS_TRADES}")
        reject = True
    if len(stats["symbols"]) < MIN_SYMBOLS:
        reasons.append(f"symbols {len(stats['symbols'])} < {MIN_SYMBOLS}")
        reject = True
    if oos_stats["avg_r"] <= MIN_OOS_AVG_R:
        reasons.append(f"OOS avg R {oos_stats['avg_r']} <= {MIN_OOS_AVG_R}")
        reject = True
    if oos_stats["win_rate"] < MIN_OOS_WIN_RATE:
        reasons.append(f"OOS win rate {oos_stats['win_rate']}% < {MIN_OOS_WIN_RATE}%")
        reject = True
    if stats["profit_factor"] < MIN_PROFIT_FACTOR:
        reasons.append(f"PF {stats['profit_factor']} < {MIN_PROFIT_FACTOR}")
        reject = True
    if stats["max_consec"] > MAX_CONSEC_LOSSES:
        reasons.append(f"max consec {stats['max_consec']} > {MAX_CONSEC_LOSSES}")
        reject = True
    if is_stats["avg_r"] > 0 and oos_stats["avg_r"] <= 0:
        reasons.append("overfit: IS positive but OOS negative")
        reject = True

    if reject:
        if len(reasons) <= 2:
            return "OBSERVE_ONLY", reasons
        return "REJECTED", reasons

    # Promotion criteria
    if (oos_stats["avg_r"] >= MIN_OOS_AVG_R and
        oos_stats["win_rate"] >= MIN_OOS_WIN_RATE and
        stats["profit_factor"] >= MIN_PROFIT_FACTOR and
        stats["max_dd"] < MAX_MAX_DD):
        return "PAPER_PRIORITY", reasons
    else:
        return "PAPER_CANDIDATE", reasons
