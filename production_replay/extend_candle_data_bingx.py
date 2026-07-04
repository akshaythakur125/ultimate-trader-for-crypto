"""Extend candle cache on BingX specifically for remaining symbols."""
import json, os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")


def ccxt_to_dict(candle):
    return {
        "timestamp": str(candle[0]),
        "open": candle[1],
        "high": candle[2],
        "low": candle[3],
        "close": candle[4],
        "volume": candle[5],
    }


def main():
    import ccxt
    ex = ccxt.bingx()
    ex.load_markets()
    print(f"BingX markets loaded: {len(ex.markets)}")

    symbols = sorted([f.replace("_1h.json", "") for f in os.listdir(CACHE_DIR) if f.endswith("_1h.json")])
    print(f"Total symbols: {len(symbols)}")

    need_extend = []
    for cache_sym in symbols:
        path = os.path.join(CACHE_DIR, f"{cache_sym}_1h.json")
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) < 200:
                ccxt_sym = cache_sym.replace("_", "/")
                if ccxt_sym in ex.markets:
                    need_extend.append((cache_sym, ccxt_sym))
        except Exception:
            pass

    print(f"Need extension: {len(need_extend)}")

    ok = 0
    fail = 0
    skip = 0
    total = len(need_extend)

    for idx, (cache_sym, ccxt_sym) in enumerate(need_extend, 1):
        try:
            since_ms = int((datetime.now(timezone.utc).timestamp() - 30 * 86400) * 1000)
            all_candles = []
            while True:
                candles = ex.fetch_ohlcv(ccxt_sym, "1h", since=since_ms, limit=1000)
                if not candles:
                    break
                all_candles.extend(candles)
                if len(candles) < 1000:
                    break
                since_ms = candles[-1][0] + 1
                time.sleep(0.3)

            if not all_candles:
                skip += 1
                if idx % 10 == 0:
                    print(f"  [{idx}/{total}] {cache_sym}: NO_DATA")
                continue

            seen = set()
            deduped = []
            for c in all_candles:
                ts = c[0]
                if ts not in seen:
                    seen.add(ts)
                    deduped.append(c)
            deduped.sort(key=lambda x: x[0])

            new_data = [ccxt_to_dict(c) for c in deduped]
            path = os.path.join(CACHE_DIR, f"{cache_sym}_1h.json")
            with open(path, "w") as f:
                json.dump(new_data, f)

            days = (deduped[-1][0] - deduped[0][0]) / 86400000
            ok += 1

            if idx % 10 == 0 or idx == 1:
                print(f"  [{idx}/{total}] {cache_sym:20s} {len(new_data)} candles ({days:.1f}d)")

        except Exception as e:
            fail += 1
            if idx % 10 == 0:
                print(f"  [{idx}/{total}] {cache_sym}: FAILED {str(e)[:30]}")
            time.sleep(1)

    print(f"\nDone: OK={ok} Fail={fail} Skip={skip}")

    print("\nFinal candle counts:")
    lengths = []
    for f in sorted(os.listdir(CACHE_DIR))[:100]:
        if f.endswith("_1h.json"):
            try:
                d = json.load(open(os.path.join(CACHE_DIR, f)))
                if isinstance(d, list):
                    lengths.append(len(d))
            except Exception:
                pass
    if lengths:
        print(f"  Sample: min={min(lengths)} max={max(lengths)} avg={sum(lengths)/len(lengths):.1f}")
        print(f"  >=200: {sum(1 for l in lengths if l >= 200)}")
        print(f"  <200:  {sum(1 for l in lengths if l < 200)}")


if __name__ == "__main__":
    main()
