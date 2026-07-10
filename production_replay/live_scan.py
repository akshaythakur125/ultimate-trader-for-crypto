"""Fetch fresh 1h candles from BingX, scan for BB Bounce v1 signals live."""
import json, os, sys, time, ccxt
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from production_replay.breadwinner_strategy_library import detect_bb_bounce

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "candles_cache")
OPEN_ORDERS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "open_orders.json")
TRADE_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "trade_log.jsonl")

MAX_TRADES = 3
MAX_NOTIONAL_PER_TRADE = 5.0
MAX_TOTAL_NOTIONAL = 10.0
MAX_RETRIES = 3
MIN_NOTIONAL = 5.0
BB_PERIOD = 15
BB_STD_MULT = 3.5
BB_RR_TARGET = 10.0
BB_MIN_ENTRY_VOL_RATIO = 1.5
RISK_PCT = 0.005
STOP_MULTIPLIER = RISK_PCT
TARGET_MULTIPLIER = RISK_PCT * BB_RR_TARGET


def load_cached(cache_sym):
    path = os.path.join(CACHE_DIR, f"{cache_sym}_1h.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_cache(cache_sym, candles):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{cache_sym}_1h.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(candles, f)
    os.replace(tmp, path)


def load_open_orders():
    try:
        with open(OPEN_ORDERS_PATH) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [o for o in data if isinstance(o, dict) and "symbol" in o and "entry" in o]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_open_orders(orders):
    os.makedirs(os.path.dirname(OPEN_ORDERS_PATH), exist_ok=True)
    tmp = OPEN_ORDERS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(orders, f, indent=2)
    os.replace(tmp, OPEN_ORDERS_PATH)


def log_trade(entry):
    os.makedirs(os.path.dirname(TRADE_LOG_PATH), exist_ok=True)
    with open(TRADE_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def ccxt_to_dict(candle):
    return {
        "timestamp": str(candle[0]),
        "open": candle[1],
        "high": candle[2],
        "low": candle[3],
        "close": candle[4],
        "volume": candle[5],
    }


def fetch_ohlcv_with_retry(ex, symbol, timeframe, limit):
    for attempt in range(MAX_RETRIES):
        try:
            return ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1 * (attempt + 1))
            else:
                raise


def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def close_position_market(ex_client, sym, side, qty):
    close_side = "sell" if side == "LONG" else "buy"
    try:
        positions = ex_client.fetch_positions()
        has_position = False
        for p in positions:
            if p["symbol"] == sym and abs(safe_float(p.get("contracts", 0))) > 0:
                has_position = True
                break
        if not has_position:
            print(f"    >>> NO POSITION TO CLOSE: {sym}")
            return True
        order = ex_client.create_market_order(sym, close_side, qty)
        print(f"    >>> EMERGENCY CLOSE: {sym} {close_side} {qty} (order={order.get('id')})")
        return True
    except Exception as e:
        print(f"    >>> EMERGENCY CLOSE FAILED: {sym} {e} — MANUAL INTERVENTION NEEDED")
        return False


def sync_positions_with_exchange(ex_client, tracked_orders):
    """Verify tracked orders against actual BingX positions. Remove orphaned tracking."""
    if not tracked_orders:
        return tracked_orders

    try:
        positions = ex_client.fetch_positions()
        active_positions = {}
        for p in positions:
            amt = safe_float(p.get("contracts", 0))
            if abs(amt) > 0:
                active_positions[p["symbol"]] = p
    except Exception as e:
        print(f"  >>> POSITION SYNC FAILED: {e} — keeping tracked orders as-is")
        return tracked_orders

    verified = []
    for trade in tracked_orders:
        sym = trade["symbol"]
        if sym in active_positions:
            verified.append(trade)
        else:
            print(f"  >>> ORPHAN CLEANED: {sym} — no position on BingX")
            log_trade({"event": "orphan_cleaned", "symbol": sym,
                       "timestamp": datetime.now(timezone.utc).isoformat()})

    if len(tracked_orders) != len(verified):
        print(f"  Positions synced: {len(tracked_orders)} tracked -> {len(verified)} with active positions")

    return verified


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
        sl_hit = False
        tp_hit = False

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
                    sl_hit = True
            except Exception as e:
                print(f"    >>> SL CHECK FAILED: {sym} {e}")

        if tp_order_id and not sl_hit:
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
                    tp_hit = True
            except Exception as e:
                print(f"    >>> TP CHECK FAILED: {sym} {e}")

        if not sl_hit and not tp_hit:
            updated.append(trade)
        else:
            outcome = "STOP" if sl_hit else "TARGET"
            log_trade({"event": "closed", "symbol": sym, "outcome": outcome,
                       "entry": trade.get("entry"), "qty": trade.get("qty"),
                       "timestamp": datetime.now(timezone.utc).isoformat()})
            print(f"    >>> TRADE CLOSED: {sym} ({outcome})")

    save_open_orders(updated)
    if len(open_orders) != len(updated):
        print(f"  Orders cleaned: {len(open_orders)} -> {len(updated)}")


print("Connecting to BingX...")
ex = ccxt.bingx()
ex.load_markets()
print(f"Markets loaded: {len(ex.markets)}")

if os.environ.get("BINGX_EXECUTION_MODE") == "live":
    apikey = os.environ.get("BINGX_API_KEY")
    apisec = os.environ.get("BINGX_API_SECRET")
    if apikey and apisec:
        ex_client = ccxt.bingx({"apiKey": apikey, "secret": apisec})
        cancel_orphaned_orders(ex_client)
        open_orders = load_open_orders()
        if open_orders:
            open_orders = sync_positions_with_exchange(ex_client, open_orders)
            save_open_orders(open_orders)

os.makedirs(CACHE_DIR, exist_ok=True)
symbols_in_cache = sorted([f.replace("_1h.json", "") for f in os.listdir(CACHE_DIR) if f.endswith("_1h.json")])
if not symbols_in_cache:
    symbols_in_cache = [s.replace("/", "_") for s in ex.markets if s.endswith("/USDT")][:200]

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
        candles = fetch_ohlcv_with_retry(ex, ccxt_sym, "1h", 30)
        if not candles:
            fail += 1
            continue

        cached = load_cached(cs)
        cached_map = {c["timestamp"]: c for c in cached if isinstance(c, dict)}
        new = [ccxt_to_dict(c) for c in candles]

        for n in new:
            cached_map[n["timestamp"]] = n

        merged = sorted(cached_map.values(), key=lambda x: int(x["timestamp"]))

        if len(merged) < BB_PERIOD + 6:
            fail += 1
            continue

        ok += 1

        check_idx = len(merged) - 3
        if check_idx < BB_PERIOD + 5:
            fail += 1
            continue

        sig = detect_bb_bounce(merged, check_idx, period=BB_PERIOD, std_mult=BB_STD_MULT,
                               rr_target=BB_RR_TARGET, min_entry_volume_ratio=BB_MIN_ENTRY_VOL_RATIO)
        if sig:
            trigger_c = merged[check_idx]
            trigger_ts = datetime.fromtimestamp(int(trigger_c["timestamp"]) / 1000, tz=timezone.utc)
            sig["symbol"] = cs
            sig["trigger_ts"] = trigger_ts.isoformat()
            sig["trigger_close"] = trigger_c["close"]
            sig["candle_idx"] = check_idx
            sig["total_candles"] = len(merged)
            sig["current_price"] = float(merged[-1]["close"])
            signals.append(sig)

        save_cache(cs, merged)

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - start
            print(f"  [{idx+1}/{len(to_fetch)}] {cs:20s} {len(merged)} candles | {len(signals)} signals ({elapsed:.0f}s)")

    except Exception as e:
        fail += 1
        print(f"  [{cs}] ERROR: {e}")

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

if signals and os.environ.get("BINGX_EXECUTION_MODE") == "live":
    apikey = os.environ.get("BINGX_API_KEY")
    apisec = os.environ.get("BINGX_API_SECRET")
    if not apikey or not apisec:
        print("\n  LIVE mode set but missing BINGX_API_KEY/SECRET. Skipping orders.")
    else:
        ex_exec = ccxt.bingx({"apiKey": apikey, "secret": apisec})
        open_orders = load_open_orders()
        for s in signals:
            try:
                side = "buy" if s["direction"] == "LONG" else "sell"
                close_side = "sell" if s["direction"] == "LONG" else "buy"
                risk_usdt = 1.00
                diff = abs(s["entry"] - s["stop"])
                if diff <= 0:
                    print(f"    >>> SKIPPED: {s['symbol']} — zero risk distance")
                    continue

                current_price = s["current_price"]
                if current_price <= 0:
                    print(f"    >>> SKIPPED: {s['symbol']} — zero current price")
                    continue

                qty = round(risk_usdt / diff, 4)
                if qty <= 0:
                    print(f"    >>> SKIPPED: {s['symbol']} — qty too small")
                    continue

                sym = s["symbol"].replace("_", "/") + ":USDT"

                if sym not in ex_exec.markets:
                    print(f"    >>> SKIPPED: {sym} — not available on BingX")
                    continue

                market_info = ex_exec.markets.get(sym, {})
                min_qty = safe_float(market_info.get("limits", {}).get("amount", {}).get("min"), 0.001)
                min_notional = safe_float(market_info.get("limits", {}).get("cost", {}).get("min"), MIN_NOTIONAL)

                max_qty_for_notional = round(MAX_NOTIONAL_PER_TRADE / current_price, 4)
                if min_qty * current_price > MAX_NOTIONAL_PER_TRADE:
                    print(f"    >>> SKIPPED: {sym} — min notional ${min_qty * current_price:.2f} > max ${MAX_NOTIONAL_PER_TRADE}")
                    continue

                if qty < min_qty:
                    qty = min_qty

                notional = qty * current_price
                if notional < min_notional:
                    qty = round(min_notional / current_price, 4)
                    notional = qty * current_price

                if qty < min_qty:
                    print(f"    >>> SKIPPED: {sym} — qty {qty} < min {min_qty} after notional adjustment")
                    continue

                if notional > MAX_NOTIONAL_PER_TRADE:
                    qty = max_qty_for_notional
                    notional = qty * current_price
                    print(f"    >>> QTY CAPPED: {sym} notional=${notional:.2f}")

                open_orders = load_open_orders()
                if any(o["symbol"] == sym for o in open_orders):
                    print(f"    >>> SKIPPED: {sym} — already has open orders")
                    continue

                if len(open_orders) >= MAX_TRADES:
                    print(f"    >>> SKIPPED: {sym} — max {MAX_TRADES} trades reached")
                    continue

                total_notional = sum(
                    o.get("qty", 0) * o.get("entry", 0)
                    for o in open_orders
                    if o.get("entry", 0) > 0 and o.get("qty", 0) > 0
                ) + notional
                if total_notional > MAX_TOTAL_NOTIONAL:
                    print(f"    >>> SKIPPED: {sym} — total notional ${total_notional:.2f} > ${MAX_TOTAL_NOTIONAL}")
                    continue

                try:
                    ex_exec.set_leverage(2, sym, params={"side": s["direction"]})
                except Exception as e:
                    try:
                        ex_exec.set_leverage(2, sym)
                    except Exception as e2:
                        print(f"    >>> LEVERAGE FAILED: {sym} {e2}")
                        continue

                entry_order = ex_exec.create_market_order(sym, side, qty)
                if not entry_order or not entry_order.get("id"):
                    print(f"    >>> ENTRY FAILED: {sym} — no order ID returned")
                    continue

                entry_order_id = entry_order.get("id")
                actual_entry = safe_float(entry_order.get("average"), 0)
                if actual_entry <= 0:
                    actual_entry = safe_float(entry_order.get("price"), 0)
                if actual_entry <= 0:
                    actual_entry = current_price

                if s["direction"] == "LONG":
                    actual_stop = actual_entry * (1 - STOP_MULTIPLIER)
                    actual_target = actual_entry * (1 + TARGET_MULTIPLIER)
                else:
                    actual_stop = actual_entry * (1 + STOP_MULTIPLIER)
                    actual_target = actual_entry * (1 - TARGET_MULTIPLIER)

                sl_order_id = None
                tp_order_id = None

                try:
                    sl_order = ex_exec.create_order(
                        sym, "STOP_MARKET", close_side, qty, None,
                        params={"stopPrice": actual_stop, "workingType": "MARK_PRICE"}
                    )
                    sl_order_id = sl_order.get("id")
                    print(f"    >>> STOP-LOSS: {sym} {close_side} {qty} @ {actual_stop} (order={sl_order_id})")
                except Exception as e:
                    print(f"    >>> STOP-LOSS FAILED: {sym} {e} — CLOSING POSITION")
                    closed = close_position_market(ex_exec, sym, s["direction"], qty)
                    log_trade({"event": "entry_failed_sl_closed", "symbol": sym, "direction": s["direction"],
                               "qty": qty, "entry": actual_entry, "order_id": entry_order_id,
                               "closed": closed, "error": str(e),
                               "timestamp": datetime.now(timezone.utc).isoformat()})
                    continue

                try:
                    tp_order = ex_exec.create_order(
                        sym, "TAKE_PROFIT_MARKET", close_side, qty, None,
                        params={"stopPrice": actual_target, "workingType": "MARK_PRICE"}
                    )
                    tp_order_id = tp_order.get("id")
                    print(f"    >>> TAKE-PROFIT: {sym} {close_side} {qty} @ {actual_target} (order={tp_order_id})")
                except Exception as e:
                    print(f"    >>> TAKE-PROFIT FAILED: {sym} {e} — CLOSING POSITION")
                    try:
                        ex_exec.cancel_order(sl_order_id, sym)
                        print(f"    >>> SL CANCELLED: {sym}")
                    except Exception as e2:
                        print(f"    >>> SL CANCEL ALSO FAILED: {sym} {e2}")
                    closed = close_position_market(ex_exec, sym, s["direction"], qty)
                    log_trade({"event": "entry_failed_tp_closed", "symbol": sym, "direction": s["direction"],
                               "qty": qty, "entry": actual_entry, "order_id": entry_order_id,
                               "closed": closed, "error": str(e),
                               "timestamp": datetime.now(timezone.utc).isoformat()})
                    continue

                log_trade({"event": "entry", "symbol": sym, "direction": s["direction"],
                           "qty": qty, "entry": actual_entry, "stop": actual_stop,
                           "target": actual_target, "entry_order_id": entry_order_id,
                           "sl_order_id": sl_order_id, "tp_order_id": tp_order_id,
                           "timestamp": datetime.now(timezone.utc).isoformat()})
                print(f"    >>> ENTRY: {sym} {side} {qty} @ {actual_entry} (order={entry_order_id})")

                open_orders.append({
                    "symbol": sym,
                    "direction": s["direction"],
                    "entry": actual_entry,
                    "stop": actual_stop,
                    "target": actual_target,
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
    print(f"\n  Paper only. Set BINGX_EXECUTION_MODE=live for real orders.")
