"""Historical replay engine — walk-forward candle-by-candle simulation.

Walks through OHLCV data one candle at a time, detects setups using only
information available up to that candle, simulates entries/stops/targets,
and records outcomes without lookahead bias.

Offline research only — never enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone
from statistics import mean

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")

TRADES_LEDGER = os.path.join(STATE_DIR, "historical_replay_trades.jsonl")

# Fee estimate: 0.04% per side (BingX typical)
FEE_RATE = 0.0004

# Max holding time in candles (4h candles * 30 = 120 hours = 5 days)
MAX_HOLDING_CANDLES = {
    "15m": 480,   # 5 days
    "30m": 240,
    "1h": 120,
    "4h": 30,
}


def _atr(candles: list, period: int = 14) -> float:
    """Compute Average True Range from candles list."""
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(len(candles) - period, len(candles)):
        if i == 0:
            continue
        h = float(candles[i][2])
        l = float(candles[i][3])
        pc = float(candles[i - 1][4])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return mean(trs) if trs else 0.0


def _sma(values: list, period: int) -> float:
    if len(values) < period:
        return mean(values) if values else 0.0
    return mean(values[-period:])


def _detect_sweep(candles: list, i: int, lookback: int = 20) -> dict | None:
    """Detect sweep/liquidity grab at candle i.
    
    SHORT: price swept above recent highs then closed back down (bearish rejection).
    LONG: price swept below recent lows then closed back up (bullish rejection).
    """
    if i < lookback + 2:
        return None
    c = candles[i]
    prev = candles[i - 1]
    high = float(c[2])
    low = float(c[3])
    close = float(c[4])
    open_p = float(c[1])

    recent_highs = [float(candles[j][2]) for j in range(i - lookback, i)]
    recent_lows = [float(candles[j][3]) for j in range(i - lookback, i)]
    max_recent_high = max(recent_highs)
    min_recent_low = min(recent_lows)

    signals = []

    # Bearish sweep (SHORT): price swept above recent high, closed back inside
    if high > max_recent_high and close < high and close < open_p:
        entry = close
        stop = high * 1.002  # 0.2% buffer
        risk_pct = abs(stop - entry) / entry if entry else 0
        if risk_pct > 0.001:  # at least 0.1% risk
            signals.append({
                "direction": "SHORT",
                "pattern": "sweep",
                "entry": entry,
                "stop": stop,
                "confidence": "medium",
                "entry_time": int(c[0]),
            })

    # Bullish sweep (LONG): price swept below recent low, closed back up
    if low < min_recent_low and close > low and close > open_p:
        entry = close
        stop = low * 0.998  # 0.2% buffer
        risk_pct = abs(entry - stop) / entry if entry else 0
        if risk_pct > 0.001:
            signals.append({
                "direction": "LONG",
                "pattern": "sweep",
                "entry": entry,
                "stop": stop,
                "confidence": "medium",
                "entry_time": int(c[0]),
            })

    return signals[0] if signals else None


def _detect_wick_rejection(candles: list, i: int) -> dict | None:
    """Detect wick rejection at candle i.
    
    Long upper wick + bearish close = SHORT.
    Long lower wick + bullish close = LONG.
    """
    if i < 1:
        return None
    c = candles[i]
    high = float(c[2])
    low = float(c[3])
    close = float(c[4])
    open_p = float(c[1])

    body = abs(close - open_p)
    upper_wick = high - max(open_p, close)
    lower_wick = min(open_p, close) - low

    if body <= 0:
        return None

    signals = []

    # Bearish wick rejection (SHORT): upper wick >= 2x body, bearish close
    if upper_wick >= 2 * body and close < open_p:
        entry = close
        stop = high * 1.002
        signals.append({
            "direction": "SHORT",
            "pattern": "wick_rejection",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if upper_wick < 3 * body else "medium",
            "entry_time": int(c[0]),
        })

    # Bullish wick rejection (LONG): lower wick >= 2x body, bullish close
    if lower_wick >= 2 * body and close > open_p:
        entry = close
        stop = low * 0.998
        signals.append({
            "direction": "LONG",
            "pattern": "wick_rejection",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if lower_wick < 3 * body else "medium",
            "entry_time": int(c[0]),
        })

    return signals[0] if signals else None


def _detect_compression_breakout(candles: list, i: int, lookback: int = 10) -> dict | None:
    """Detect compression (tight range) followed by expansion at candle i."""
    if i < lookback + 1:
        return None
    c = candles[i]
    high = float(c[2])
    low = float(c[3])
    close = float(c[4])
    open_p = float(c[1])

    recent_ranges = []
    for j in range(i - lookback, i):
        h = float(candles[j][2])
        l_ = float(candles[j][3])
        recent_ranges.append((h - l_) / l_ if l_ else 0)

    avg_range = mean(recent_ranges) if recent_ranges else 0
    current_range = (high - low) / low if low else 0

    if avg_range <= 0 or current_range <= 0:
        return None

    # Compression: recent range is small
    compression_ratio = current_range / avg_range if avg_range else 0

    if compression_ratio < 0.5:
        return None  # Still compressing

    # Breakout direction
    atr_val = _atr(candles[:i + 1], 14)
    if atr_val <= 0:
        return None

    signals = []

    # Bullish breakout: close > open and close near high
    if close > open_p and (high - close) < (high - low) * 0.3:
        entry = close
        stop = low - atr_val * 0.5
        signals.append({
            "direction": "LONG",
            "pattern": "compression_breakout",
            "entry": entry,
            "stop": stop,
            "confidence": "low",
            "entry_time": int(c[0]),
        })

    # Bearish breakout: close < open and close near low
    if close < open_p and (close - low) < (high - low) * 0.3:
        entry = close
        stop = high + atr_val * 0.5
        signals.append({
            "direction": "SHORT",
            "pattern": "compression_breakout",
            "entry": entry,
            "stop": stop,
            "confidence": "low",
            "entry_time": int(c[0]),
        })

    return signals[0] if signals else None


def _detect_volume_spike(candles: list, i: int, lookback: int = 20) -> dict | None:
    """Detect volume spike at candle i combined with directional move."""
    if i < lookback + 1:
        return None
    c = candles[i]
    vol = float(c[5])
    close = float(c[4])
    open_p = float(c[1])
    high = float(c[2])
    low = float(c[3])

    avg_vol = _sma([float(candles[j][5]) for j in range(i - lookback, i)], lookback)
    if avg_vol <= 0:
        return None

    vol_ratio = vol / avg_vol
    if vol_ratio < 1.5:
        return None

    atr_val = _atr(candles[:i + 1], 14)
    if atr_val <= 0:
        return None

    signals = []

    # Bullish volume spike
    if close > open_p and (high - close) < (high - low) * 0.3:
        entry = close
        stop = low - atr_val * 0.5
        signals.append({
            "direction": "LONG",
            "pattern": "volume_spike",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if vol_ratio < 2 else "medium",
            "entry_time": int(c[0]),
        })

    # Bearish volume spike
    if close < open_p and (close - low) < (high - low) * 0.3:
        entry = close
        stop = high + atr_val * 0.5
        signals.append({
            "direction": "SHORT",
            "pattern": "volume_spike",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if vol_ratio < 2 else "medium",
            "entry_time": int(c[0]),
        })

    return signals[0] if signals else None


def _calculate_rr_target(entry: float, stop: float, direction: str, min_rr: float = 4.0) -> float | None:
    """Calculate target price for a given RR. Returns None if risk is too small."""
    risk = abs(entry - stop)
    if risk <= 0 or entry <= 0:
        return None
    reward = risk * min_rr
    if direction == "LONG":
        return entry + reward
    else:
        return entry - reward


def _simulate_trade(candles: list, signal: dict, entry_idx: int, timeframe: str) -> dict:
    """Simulate a trade forward from entry_idx. Returns trade result dict.
    
    Walks forward candle by candle (no lookahead — only uses past data).
    """
    entry = signal["entry"]
    stop = signal["stop"]
    direction = signal["direction"]
    target = _calculate_rr_target(entry, stop, direction, 4.0)

    if target is None:
        return {**signal, "outcome": "INVALID", "r_result": 0.0, "exit_reason": "invalid_setup"}

    max_holding = MAX_HOLDING_CANDLES.get(timeframe, 120)

    outcome = "EXPIRED"
    exit_price = entry
    exit_reason = "max_holding_expired"
    hit_idx = entry_idx

    for j in range(entry_idx + 1, min(len(candles), entry_idx + max_holding + 1)):
        hit_idx = j
        c = candles[j]
        high = float(c[2])
        low = float(c[3])
        close = float(c[4])

        if direction == "LONG":
            if high >= target:
                outcome = "WIN"
                exit_price = target
                exit_reason = "TARGET_HIT"
                break
            if low <= stop:
                outcome = "LOSS"
                exit_price = stop
                exit_reason = "STOP_HIT"
                break
        else:  # SHORT
            if low <= target:
                outcome = "WIN"
                exit_price = target
                exit_reason = "TARGET_HIT"
                break
            if high >= stop:
                outcome = "LOSS"
                exit_price = stop
                exit_reason = "STOP_HIT"
                break

    # Calculate R
    risk = abs(entry - stop)
    pnl = (exit_price - entry) * (1 if direction == "LONG" else -1)
    r_result = round(pnl / risk, 2) if risk > 0 else 0.0

    # Apply fees (0.04% per side, so 0.08% round trip)
    fee_cost = entry * FEE_RATE * 2
    r_after_fees = round((pnl - fee_cost) / risk, 2) if risk > 0 else 0.0

    # Max favorable/adverse excursion
    max_fav = 0.0
    max_adv = 0.0
    for j in range(entry_idx + 1, hit_idx + 1):
        c = candles[j]
        high = float(c[2])
        low = float(c[3])
        if direction == "LONG":
            mfe = (high - entry) / entry if entry else 0
            mae = (entry - low) / entry if entry else 0
        else:
            mfe = (entry - low) / entry if entry else 0
            mae = (high - entry) / entry if entry else 0
        max_fav = max(max_fav, mfe)
        max_adv = max(max_adv, mae)

    holding_candles = hit_idx - entry_idx

    return {
        "symbol": signal.get("symbol", "?"),
        "direction": direction,
        "timeframe": timeframe,
        "pattern": signal.get("pattern", "unknown"),
        "entry_time": signal.get("entry_time", 0),
        "entry_price": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "exit_time": int(candles[hit_idx][0]) if hit_idx < len(candles) else 0,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "outcome": outcome,
        "r_result": r_result,
        "r_after_fees": r_after_fees,
        "holding_candles": holding_candles,
        "max_favorable_excursion_pct": round(max_fav * 100, 2),
        "max_adverse_excursion_pct": round(max_adv * 100, 2),
        "is_win": outcome == "WIN",
    }


def run_replay(
    ohlcv_data: dict[str, list],
    timeframes: list[str] | None = None,
) -> list[dict]:
    """Run historical replay on OHLCV data.
    
    Args:
        ohlcv_data: dict of symbol -> list of candles [[ts, o, h, l, c, v], ...]
        timeframes: list of timeframe strings to simulate (default: all from data)
    
    Returns:
        List of simulated trade result dicts.
    """
    if timeframes is None:
        timeframes = ["1h"]

    all_trades = []
    seen_signals = set()

    for symbol, candles in ohlcv_data.items():
        if len(candles) < 50:
            continue

        for tf in timeframes:
            max_hold = MAX_HOLDING_CANDLES.get(tf, 120)

            for i in range(30, len(candles) - 1):
                # Detect setups using only data up to candle i
                detectors = [
                    _detect_sweep(candles, i),
                    _detect_wick_rejection(candles, i),
                    _detect_compression_breakout(candles, i),
                    _detect_volume_spike(candles, i),
                ]

                for signal in detectors:
                    if signal is None:
                        continue

                    # Check RR >= 4
                    risk_pct = abs(signal["stop"] - signal["entry"]) / signal["entry"] if signal["entry"] else 0
                    if risk_pct <= 0:
                        continue

                    target = _calculate_rr_target(
                        signal["entry"], signal["stop"], signal["direction"], 4.0
                    )
                    if target is None:
                        continue

                    signal["symbol"] = symbol

                    # Dedup: avoid identical signals within same candle
                    sig_key = f"{symbol}_{tf}_{signal['direction']}_{i}"
                    if sig_key in seen_signals:
                        continue
                    seen_signals.add(sig_key)

                    trade = _simulate_trade(candles, signal, i, tf)
                    all_trades.append(trade)

    return all_trades


def run_and_save(ohlcv_data: dict[str, list], timeframes: list[str] | None = None) -> list[dict]:
    """Run replay and save trades to ledger."""
    os.makedirs(STATE_DIR, exist_ok=True)
    trades = run_replay(ohlcv_data, timeframes)

    with open(TRADES_LEDGER, "w") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")

    return trades


def main():
    print("Historical Replay Engine (offline research)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
