"""Fetch fresh 1h candles from BingX, scan for BB Bounce v1 signals live."""
import json, os, sys, time, ccxt
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from production_replay.breadwinner_strategy_library import detect_bb_bounce

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "candles_cache")


def load_cached(cache_sym):
    path = os.path.join(CACHE_DIR, f"{cache_sym}_1h.json")
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return []


def save_cache(cache_sym, candles):
    path = os.path.join(CACHE_DIR, f"{cache_sym}_1h.json")
    with open(path, "w") as f:
        json.dump(candles, f)


def ccxt_to_dict(candle):
    return {
        "timestamp": str(candle[0]),
        "open": candle[1],
        "high": candle[2],
        "low": candle[3],
        "close": candle[4],
        "volume": candle[5],
    }


print("Connecting to BingX...")
ex = ccxt.bingx()
ex.load_markets()
print(f"Markets loaded: {len(ex.markets)}")

symbols_in_cache = sorted([f.replace("_1h.json", "") for f in os.listdir(CACHE_DIR) if f.endswith("_1h.json")])

to_fetch = []
for cs in symbols_in_cache:
    ccxt_sym = cs.replace("_", "/")
    if ccxt_sym in ex.markets:
        to_fetch.append((cs, ccxt_sym))

print(f"Will fetch fresh data for {len(to_fetch)} symbols...")

signals = []
ok = fail = 0
start = time.time()

for idx, (cs, ccxt_sym) in enumerate(to_fetch):
    try:
        candles = ex.fetch_ohlcv(ccxt_sym, "1h", limit=30)
        if not candles:
            fail += 1
            continue

        cached = load_cached(cs)
        cached_map = {c["timestamp"]: c for c in cached if isinstance(c, dict)}
        new = [ccxt_to_dict(c) for c in candles]

        for n in new:
            cached_map[n["timestamp"]] = n

        merged = sorted(cached_map.values(), key=lambda x: int(x["timestamp"]))

        if len(merged) < 20:
            fail += 1
            continue

        ok += 1

        for i in [len(merged) - 3]:  # ponytail: only last candle trigger = max 1h stale
            sig = detect_bb_bounce(merged, i, period=15, std_mult=3.5, rr_target=10.0,
                                   min_entry_volume_ratio=1.5)  # ponytail: 1.5x volume filter matches official scanner
            if sig:
                trigger_c = merged[i]
                trigger_ts = datetime.fromtimestamp(int(trigger_c["timestamp"]) / 1000, tz=timezone.utc)
                sig["symbol"] = cs
                sig["trigger_ts"] = trigger_ts.isoformat()
                sig["trigger_close"] = trigger_c["close"]
                sig["candle_idx"] = i
                sig["total_candles"] = len(merged)
                signals.append(sig)
                break

        save_cache(cs, merged)

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - start
            print(f"  [{idx+1}/{len(to_fetch)}] {cs:20s} {len(merged)} candles | {len(signals)} signals ({elapsed:.0f}s)")

    except Exception as e:
        fail += 1

    time.sleep(0.15)

elapsed = time.time() - start
print(f"\nDone in {elapsed:.0f}s: OK={ok} Fail={fail}")

print(f"\n{'='*70}")
print(f"  BB BOUNCE v1 - LIVE SIGNALS ({datetime.now(timezone.utc).isoformat()})")
print(f"{'='*70}")

if not signals:
    print("\n  No actionable BB Bounce signals found right now.")
    print("  (Market is quiet - no closes outside 3.5s bands)")
else:
    for s in sorted(signals, key=lambda x: x["candle_idx"], reverse=True):
        risk = abs(s['entry'] - s['stop'])
        reward = abs(s['entry'] - s['target'])
        rr = reward / risk if risk > 0 else 0
        print(f"\n  {s['symbol']}/USDT  {s['direction']:5s}  {s['pattern']}")
        print(f"    Trigger: {s['trigger_ts']}  Close={s['trigger_close']}")
        print(f"    Entry:   {s['entry']:.6f}  Stop={s['stop']:.6f}  Target={s['target']:.6f}")
        print(f"    Risk/unit: {risk:.6f}  Reward/unit: {reward:.6f}  RR=1:{rr:.0f}")
        if 'entry_volume_ratio' in s:
            print(f"    Entry vol: {s['entry_volume_ratio']:.2f}x avg")

print(f"\n  Paper only. No real orders.")