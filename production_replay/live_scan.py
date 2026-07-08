"""Fetch fresh 1h candles from BingX, scan for BB Bounce v1 signals live."""
import json, os, sys, time, ccxt
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from production_replay.breadwinner_strategy_library import detect_bb_bounce

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "candles_cache")
OPEN_ORDERS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "open_orders.json")


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


def load_open_orders():
    try:
        with open(OPEN_ORDERS_PATH) as f:
            return json.load(f)
    except:
        return []


def save_open_orders(orders):
    os.makedirs(os.path.dirname(OPEN_ORDERS_PATH), exist_ok=True)
    with open(OPEN_ORDERS_PATH, "w") as f:
        json.dump(orders, f, indent=2)


def ccxt_to_dict(candle):
    return {
        "timestamp": str(candle[0]),
        "open": candle[1],
        "high": candle[2],
        "low": candle[3],
        "close": candle[4],
        "volume": candle[5],
    }


def cancel_orphaned_orders(ex_client):
    """Check open orders and cancel the other leg when one fills."""
    open_orders = load_open_orders()
    if not open_orders:
        return

    updated = []
    for trade in open_orders:
        sym = trade["symbol"]
        sl_order_id = trade.get("sl_order_id")
        tp_order_id = trade.get("tp_order_id")
        sl_cancelled = False
        tp_cancelled = False

        # Check stop-loss order status
        if sl_order_id:
            try:
                sl_status = ex_client.fetch_order(sl_order_id, sym)
                if sl_status["status"] in ("closed", "filled"):
                    print(f"    >>> STOP HIT: {sym} — cancelling take-profit")
                    if tp_order_id:
                        try:
                            ex_client.cancel_order(tp_order_id, sym)
                            print(f"    >>> TP CANCELLED: {sym} {tp_order_id}")
                        except Exception as e:
                            print(f"    >>> TP CANCEL FAILED: {sym} {e}")
                    sl_cancelled = True
                elif sl_status["status"] == "canceled":
                    sl_cancelled = True
            except Exception:
                pass

        # Check take-profit order status
        if tp_order_id and not sl_cancelled:
            try:
                tp_status = ex_client.fetch_order(tp_order_id, sym)
                if tp_status["status"] in ("closed", "filled"):
                    print(f"    >>> TARGET HIT: {sym} — cancelling stop-loss")
                    if sl_order_id:
                        try:
                            ex_client.cancel_order(sl_order_id, sym)
                            print(f"    >>> SL CANCELLED: {sym} {sl_order_id}")
                        except Exception as e:
                            print(f"    >>> SL CANCEL FAILED: {sym} {e}")
                    tp_cancelled = True
                elif tp_status["status"] == "canceled":
                    tp_cancelled = True
            except Exception:
                pass

        # Keep trade in list if both legs still active
        if not sl_cancelled and not tp_cancelled:
            updated.append(trade)
        else:
            print(f"    >>> TRADE CLOSED: {sym}")

    save_open_orders(updated)
    if len(open_orders) != len(updated):
        print(f"  Orders cleaned: {len(open_orders)} -> {len(updated)}")


print("Connecting to BingX...")
ex = ccxt.bingx()
ex.load_markets()
print(f"Markets loaded: {len(ex.markets)}")

# Auto-cancel orphaned orders from previous runs
if os.environ.get("BINGX_EXECUTION_MODE") == "live":
    apikey = os.environ.get("BINGX_API_KEY")
    apisec = os.environ.get("BINGX_API_SECRET")
    if apikey and apisec:
        ex_client = ccxt.bingx({"apiKey": apikey, "secret": apisec})
        cancel_orphaned_orders(ex_client)

symbols_in_cache = sorted([f.replace("_1h.json", "") for f in os.listdir(CACHE_DIR) if f.endswith("_1h.json")])
if not symbols_in_cache:
    symbols_in_cache = [s.replace("/", "_") for s in ex.markets if s.endswith("/USDT")][:100]

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

# ponytail: real execution via ccxt when BINGX_EXECUTION_MODE=live
if signals and os.environ.get("BINGX_EXECUTION_MODE") == "live":
    apikey = os.environ.get("BINGX_API_KEY")
    apisec = os.environ.get("BINGX_API_SECRET")
    if apikey and apisec:
        ex_exec = ccxt.bingx({"apiKey": apikey, "secret": apisec})
        ex_exec.load_markets()
        open_orders = load_open_orders()
        for s in signals:
            try:
                side = "buy" if s["direction"] == "LONG" else "sell"
                close_side = "sell" if s["direction"] == "LONG" else "buy"
                risk_usdt = 1.00  # 5% of 20 capital
                diff = abs(s["entry"] - s["stop"])
                qty = round(risk_usdt / diff, 2) if diff > 0 else 0
                if qty <= 0:
                    continue
                sym = s["symbol"].replace("_", "/") + ":USDT"

                # Skip if symbol doesn't exist on BingX
                if sym not in ex_exec.markets:
                    print(f"    >>> SKIPPED: {sym} — not available on BingX")
                    continue

                # Skip if already have open order for this symbol
                if any(o["symbol"] == sym for o in open_orders):
                    print(f"    >>> SKIPPED: {sym} — already has open orders")
                    continue

                # Set leverage to 2x before placing orders
                try:
                    ex_exec.set_leverage(2, sym)
                except Exception as e:
                    print(f"    >>> LEVERAGE WARNING: {sym} {e}")

                # 1) Market entry
                entry_order = ex_exec.create_market_order(sym, side, qty)
                entry_order_id = entry_order.get("id")
                print(f"    >>> ENTRY: {sym} {side} {qty} (order={entry_order_id})")

                sl_order_id = None
                tp_order_id = None

                # 2) Stop-loss (trigger order)
                try:
                    sl_price = float(s["stop"])
                    sl_order = ex_exec.create_order(sym, "stop", close_side, qty, sl_price, params={"triggerPrice": sl_price})
                    sl_order_id = sl_order.get("id")
                    print(f"    >>> STOP-LOSS: {sym} {close_side} {qty} @ {sl_price} (order={sl_order_id})")
                except Exception as e:
                    print(f"    >>> STOP-LOSS FAILED: {s['symbol']} {e}")

                # 3) Take-profit (limit order)
                try:
                    tp_price = float(s["target"])
                    tp_order = ex_exec.create_order(sym, "limit", close_side, qty, tp_price)
                    tp_order_id = tp_order.get("id")
                    print(f"    >>> TAKE-PROFIT: {sym} {close_side} {qty} @ {tp_price} (order={tp_order_id})")
                except Exception as e:
                    print(f"    >>> TAKE-PROFIT FAILED: {s['symbol']} {e}")

                # Save order IDs for auto-cancellation
                open_orders.append({
                    "symbol": sym,
                    "direction": s["direction"],
                    "entry": float(s["entry"]),
                    "stop": float(s["stop"]),
                    "target": float(s["target"]),
                    "qty": qty,
                    "entry_order_id": entry_order_id,
                    "sl_order_id": sl_order_id,
                    "tp_order_id": tp_order_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                save_open_orders(open_orders)

            except Exception as e:
                print(f"    >>> ORDER FAILED: {s['symbol']} {e}")
    else:
        print("\n  LIVE mode set but missing BINGX_API_KEY/SECRET. Skipping orders.")
else:
    print(f"\n  Paper only. Set BINGX_EXECUTION_MODE=live for real orders.")
