"""Shared setup level computation for manual review."""
import csv, os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "historical")
ATR_PERIOD = 14
SWING_LOOKBACK = 20


def csv_path(symbol: str, timeframe: str) -> str:
    return os.path.join(DATA_DIR, f"{symbol}_{timeframe}.csv")


def load_candles(symbol: str, timeframe: str) -> list[dict]:
    path = csv_path(symbol, timeframe)
    if not os.path.exists(path):
        return []
    candles = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                candles.append({
                    "timestamp": row["timestamp"], "open": float(row["open"]),
                    "high": float(row["high"]), "low": float(row["low"]),
                    "close": float(row["close"]), "volume": float(row.get("volume", 0)),
                })
            except (KeyError, ValueError):
                continue
    return candles


def true_range(c: dict, prev: dict | None) -> float:
    if prev is None:
        return c["high"] - c["low"]
    return max(c["high"] - c["low"], abs(c["high"] - prev["close"]), abs(c["low"] - prev["close"]))


def compute_atr(candles: list[dict], period: int = ATR_PERIOD) -> float:
    if len(candles) < 2:
        return 0
    trs = []
    for i in range(1, min(period + 1, len(candles))):
        trs.append(true_range(candles[-i], candles[-i - 1] if i < len(candles) else None))
    return sum(trs) / max(len(trs), 1)


def compute_swings(candles: list[dict], lookback: int = SWING_LOOKBACK) -> tuple[float, float]:
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    swing_high = max(c["high"] for c in recent) if recent else 0
    swing_low = min(c["low"] for c in recent) if recent else 0
    return swing_high, swing_low


def infer_direction(candles: list[dict]) -> str:
    if len(candles) < 5:
        return "UNKNOWN"
    recent = candles[-5:]
    closes = [c["close"] for c in recent]
    avg_old = sum(closes[:3]) / 3 if len(closes) >= 3 else sum(closes) / len(closes)
    avg_new = sum(closes[-3:]) / 3 if len(closes) >= 3 else closes[-1]
    recent_high = max(c["high"] for c in recent)
    recent_low = min(c["low"] for c in recent)
    rw = recent_high - recent_low if recent_high > recent_low else 1
    pos = (candles[-1]["close"] - recent_low) / rw
    if avg_new > avg_old * 1.001 and pos > 0.4:
        return "LONG"
    elif avg_new < avg_old * 0.999 and pos < 0.6:
        return "SHORT"
    return "UNKNOWN"


def compute_setup_levels(candles: list[dict], atr: float, direction: str) -> dict:
    if not candles or atr <= 0:
        return {"direction": direction, "latest_close": None,
                "entry_zone": None, "stop": None,
                "target_1": None, "target_2": None, "rr_1": None, "rr_2": None}
    last = candles[-1]
    close = last["close"]
    swing_high, swing_low = compute_swings(candles)

    if direction == "LONG":
        entry = round(close, 2)
        stop = round(min(close - atr * 1.5, swing_low - atr * 0.3), 2)
        t1 = round(close + atr * 1.5, 2)
        t2 = round(close + atr * 3.0, 2)
    elif direction == "SHORT":
        entry = round(close, 2)
        stop = round(max(close + atr * 1.5, swing_high + atr * 0.3), 2)
        t1 = round(close - atr * 1.5, 2)
        t2 = round(close - atr * 3.0, 2)
    else:
        return {"direction": direction, "latest_close": close,
                "entry_zone": None, "stop": None,
                "target_1": None, "target_2": None, "rr_1": None, "rr_2": None}

    risk = abs(entry - stop)
    rr1 = round(abs(t1 - entry) / risk, 2) if risk > 0 else None
    rr2 = round(abs(t2 - entry) / risk, 2) if risk > 0 else None

    return {"direction": direction, "latest_close": close,
            "entry_zone": entry, "stop": stop,
            "target_1": t1, "target_2": t2, "rr_1": rr1, "rr_2": rr2}
