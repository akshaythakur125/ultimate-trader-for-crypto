"""Fetch fresh 1h candles from BingX, scan for BB Bounce v1 signals live."""
import json, math, os, sys, time, ccxt
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from production_replay.breadwinner_strategy_library import detect_bb_bounce

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "candles_cache")
OPEN_ORDERS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "open_orders.json")
TRADE_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_state", "trade_log.jsonl")

# Pilot sizing for ~$20 capital at 2x leverage, max 3 concurrent trades.
# Per-trade notional must exceed the exchange minimum order size (BTC ~ $6.39),
# so keep it at/above ~$10. Total is kept <= ~1.5x capital of margin used.
# 4% capital risk per trade with a 0.5% stop needs ~8x capital in notional, so
# only one such trade fits on ~$18. Concurrency is intentionally 1.
MAX_TRADES = 1
MAX_NOTIONAL_PER_TRADE = 10.0  # legacy; sizing is risk-based (see place_bracket_order)
MAX_TOTAL_NOTIONAL = 216.0
MAX_RETRIES = 3
MIN_NOTIONAL = 5.0
# Only scan/trade symbols with at least this much 24h quote volume. Excludes
# delisted/offline/dead microcaps (which have ~0 volume) so signals land on
# real, executable markets. Lower it for more (thinner) symbols, raise it for
# only the most liquid names.
MIN_24H_VOLUME_USDT = 3_000_000
BB_PERIOD = 15
BB_STD_MULT = 3.0
BB_RR_TARGET = 10.0
BB_MIN_ENTRY_VOL_RATIO = 1.5
RISK_PCT = 0.005
STOP_MULTIPLIER = RISK_PCT
TARGET_MULTIPLIER = RISK_PCT * BB_RR_TARGET
CAPITAL_USDT = 18.0
RISK_PER_TRADE_PCT = 0.04  # 4% of capital risked per trade (enforced via the stop)
LEVERAGE_CAP = 12          # max leverage the sizer will use to afford a trade


def _load_live_credentials() -> tuple[str | None, str | None]:
    api_key = os.environ.get("BINGX_API_KEY")
    api_secret = os.environ.get("BINGX_API_SECRET") or os.environ.get("BINGX_SECRET_KEY")
    # Strip stray whitespace/newlines from pasted keys. A trailing space in the
    # secret silently corrupts the HMAC signature (BingX 100001), and one in the
    # key can read as an invalid apiKey (BingX 100413).
    if api_key:
        api_key = api_key.strip()
    if api_secret:
        api_secret = api_secret.strip()
    return api_key, api_secret


def make_authed_client(apikey: str, apisec: str):
    """Authenticated BingX swap client with markets loaded.

    ccxt's load_markets() calls fetch_currencies(), which hits a spot-wallet
    endpoint that a Futures-only API key cannot access (BingX 100413). We only
    trade perps, so skip the currency fetch and load markets from the public
    endpoint. This also populates .markets so symbol/limit lookups work.
    """
    ex = ccxt.bingx({"apiKey": apikey, "secret": apisec, "enableRateLimit": True})
    ex.options["defaultType"] = "swap"
    ex.has["fetchCurrencies"] = False
    ex.load_markets()
    return ex


def _get_hedged_mode(ex_client) -> bool:
    try:
        mode = ex_client.fetch_position_mode() or {}
        return bool(mode.get("hedged", False))
    except Exception:
        return False


def _check_symbol_modes(ex_client, symbol: str) -> tuple[bool, dict]:
    report = {"symbol": symbol}
    try:
        position_mode = ex_client.fetch_position_mode(symbol) or {}
        report["hedged"] = bool(position_mode.get("hedged", False))
        report["position_mode"] = "hedged" if report["hedged"] else "one_way"
    except Exception as e:
        report["error"] = f"position mode check failed: {e}"
        return False, report

    # Margin mode is informational only — the order never sets it. Some symbols
    # don't answer the margin-mode endpoint (BingX 109425), so never block a
    # trade on it; set_leverage / create_order will still reject a genuinely
    # untradeable symbol safely.
    try:
        margin_mode = ex_client.fetch_margin_mode(symbol) or {}
        raw_margin_mode = str(
            margin_mode.get("marginMode")
            or margin_mode.get("marginType")
            or margin_mode.get("margin_mode")
            or ""
        ).lower()
        if raw_margin_mode in ("cross", "crossed"):
            raw_margin_mode = "cross"
        report["margin_mode"] = raw_margin_mode or "unknown"
    except Exception as e:
        report["margin_mode"] = "unknown"
        report["margin_warning"] = str(e)[:120]

    report["ok"] = True
    return True, report


def _market_key_to_cache_symbol(market_key: str) -> str:
    if "/" not in market_key:
        return market_key.replace(":", "")
    base, rest = market_key.split("/", 1)
    quote = rest.split(":", 1)[0]
    return f"{base}{quote}"


def _canon(sym: str) -> str:
    """Canonical key for matching cache names, market keys, and ticker keys.

    'ADA/USDT:USDT', 'ADA_USDT', and 'ADAUSDT' all normalize to 'ADAUSDT'.
    """
    return sym.split(":")[0].replace("/", "").replace("_", "").upper()


def _resolve_market_key(raw_symbol: str, markets: dict) -> str | None:
    """Resolve a signal symbol to its BingX linear-USDT SWAP market key.

    THIS IS A FUTURES BOT — it must resolve to the perpetual swap
    ('BTC/USDT:USDT'), never the spot market ('BTC/USDT'). BingX lists BOTH,
    and a signal symbol like 'COW_USDT' matches the spot key first. Sending the
    order to the spot market routes it at the empty spot wallet, so BingX
    rejects it with avail:0 InsufficientFunds even though the futures wallet is
    funded. We therefore only ever return a market whose 'swap' flag is set;
    swap-form candidates are tried first, and a match is accepted only if it is
    actually a swap. If no swap market exists for the symbol we return None so
    the trade is skipped rather than mis-routed to spot.
    """
    if not raw_symbol:
        return None
    cleaned = raw_symbol.replace("_", "/")
    base = cleaned.split(":")[0]  # strip any existing :USDT suffix
    candidates = []
    if cleaned.endswith(":USDT"):
        candidates.append(cleaned)
    if base.endswith("/USDT"):
        candidates.append(f"{base}:USDT")
    if base.endswith("USDT") and "/" not in base:
        candidates.append(f"{base[:-4]}/USDT:USDT")
    # Non-swap forms last, and only accepted below if they are actually swaps.
    candidates.extend([raw_symbol, cleaned, base])
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        market = markets.get(candidate)
        if market and market.get("swap"):
            return candidate
    return None


def _liquid_online_markets(ex) -> set:
    """market_keys that are USDT swaps with >= MIN_24H_VOLUME_USDT 24h volume.

    Filters out delisted/offline/dead microcaps (which have ~0 volume) so the
    scanner only trades real, executable markets. Returns an empty set if
    tickers can't be fetched, in which case no volume filter is applied.
    """
    try:
        tickers = ex.fetch_tickers()
    except Exception as e:
        print(f"  liquidity filter OFF — fetch_tickers failed: {type(e).__name__}: {str(e)[:100]}")
        return set()
    out = set()
    checked = 0
    for key, t in tickers.items():
        m = ex.markets.get(key, {}) or {}
        if not (m.get("swap") and m.get("quote") == "USDT"):
            continue
        checked += 1
        qv = t.get("quoteVolume")
        if not qv:
            qv = (t.get("baseVolume") or 0) * (t.get("last") or t.get("close") or 0)
        if qv and qv >= MIN_24H_VOLUME_USDT:
            out.add(_canon(key))
    print(f"  liquidity: {len(tickers)} tickers, {checked} usdt-swaps, "
          f"{len(out)} >= ${MIN_24H_VOLUME_USDT/1e6:.0f}M 24h vol")
    return out


def _discover_symbols(ex) -> list[tuple[str, str]]:
    liquid = _liquid_online_markets(ex)
    pairs = []
    cached_files = [
        f for f in os.listdir(CACHE_DIR)
        if f.endswith("_1h.json")
    ] if os.path.exists(CACHE_DIR) else []
    if cached_files:
        best = {}  # canonical symbol -> (cache_sym, market_key)
        for filename in sorted(cached_files):
            cache_sym = filename[:-8]
            market_key = _resolve_market_key(cache_sym, ex.markets)
            if not market_key or (liquid and _canon(cache_sym) not in liquid):
                continue
            c = _canon(cache_sym)
            # Dedup coins that appear under two cache-name formats; prefer the
            # underscore file, which holds the deep history.
            if c not in best or ("_" in cache_sym and "_" not in best[c][0]):
                best[c] = (cache_sym, market_key)
        pairs = list(best.values())
        if pairs:
            return pairs

    for market_key, market in ex.markets.items():
        if market.get("swap") and market.get("quote") == "USDT" and market.get("active", True):
            if liquid and _canon(market_key) not in liquid:
                continue
            pairs.append((_market_key_to_cache_symbol(market_key), market_key))
    return pairs[:200]


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


def _ensure_margin_mode(ex_exec, sym: str, mode: str = "cross") -> None:
    """Best-effort set margin mode; ignore 'no change needed' errors.

    Cross margin lets the set leverage actually reduce the order's required
    margin against the whole balance. In isolated mode BingX can demand
    near-full notional to open a position, which makes a leveraged order
    unaffordable even with leverage set.
    """
    try:
        ex_exec.set_margin_mode(mode, sym)
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in ("no need", "not modified", "already", "no change")):
            return
        print(f"    >>> margin-mode note: {sym} {str(e)[:80]}")


def _ensure_leverage(ex_exec, sym: str, target: int, position_side: str) -> bool:
    """Set leverage to `target`x and CONFIRM it stuck; only then is it safe to trade.

    This is the crux of the `avail:0` bug: sizing computes a notional that is only
    affordable at `target`x leverage. If `set_leverage` silently no-ops (throttled,
    stale session, race with a prior cycle) the symbol can still sit at 1x, where
    BingX demands ~full notional as margin and rejects the order with
    InsufficientFunds. A bare `set_leverage(...)` that raises no exception does NOT
    prove the leverage changed — so we always read it back with `fetch_leverage`
    and require `cur_lev >= target` before returning True. We retry a few times to
    ride out transient throttling, and skip cleanly (never place at the wrong
    leverage) when we can't confirm it.
    """
    last = ""
    for _ in range(3):
        try:
            ex_exec.set_leverage(target, sym, params={"side": position_side})
        except Exception as e:
            last = str(e)
            if any(k in last.lower() for k in ("offline", "not exist", "109418", "109425", "delist")):
                print(f"    >>> SKIPPED: {sym} — symbol offline/invalid")
                return False
            # "already set / no change" is fine — the read-back below is the judge.
        try:
            cur = ex_exec.fetch_leverage(sym) or {}
            cur_lev = max(safe_float(cur.get("longLeverage")), safe_float(cur.get("shortLeverage")))
            if cur_lev >= target:
                return True
            last = f"leverage is {cur_lev:.0f}x, wanted {target}x"
        except Exception as e:
            last = str(e)
        time.sleep(0.5)
    print(f"    >>> SKIPPED: {sym} — leverage not confirmed at {target}x ({last[:60]})")
    return False


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


def place_bracket_order(ex_exec, s: dict, hedged_mode: bool) -> bool:
    """Place one live market entry with attached stop-loss and take-profit.

    Single real-order code path: both the live scan loop and the manual test
    order call this, so a test order exercises exactly what a real signal does.
    Honors the same risk caps (MAX_TRADES / MAX_NOTIONAL_PER_TRADE /
    MAX_TOTAL_NOTIONAL) and payload format. Returns True only when a real entry
    order was placed.
    """
    try:
        side = "buy" if s["direction"] == "LONG" else "sell"
        risk_usdt = round(CAPITAL_USDT * RISK_PER_TRADE_PCT, 2)  # 4% of capital
        diff = abs(s["entry"] - s["stop"])
        if diff <= 0:
            print(f"    >>> SKIPPED: {s['symbol']} — zero risk distance")
            return False

        current_price = s["current_price"]
        if current_price <= 0:
            print(f"    >>> SKIPPED: {s['symbol']} — zero current price")
            return False

        sym = s.get("market_key") or _resolve_market_key(s["symbol"], ex_exec.markets)
        if not sym:
            print(f"    >>> SKIPPED: {s['symbol']} — not available on BingX")
            return False

        # One trade at a time: check the EXCHANGE for any open position (the
        # balance 'free' field is unreliable and reports full balance even when
        # a position holds the margin). A single 4% position uses ~80% of an $18
        # account, so a second can't be funded and would just fail with avail:0.
        try:
            open_pos = [p for p in ex_exec.fetch_positions()
                        if abs(safe_float(p.get("contracts"), 0)) > 0]
        except Exception:
            open_pos = []
        if open_pos:
            held = ", ".join(str(p.get("symbol", "?")) for p in open_pos)
            print(f"    >>> SKIPPED: {sym} — position already open ({held}); one trade at a time")
            return False

        market_info = ex_exec.markets.get(sym, {}) or {}
        limits = market_info.get("limits") or {}
        amount_limits = limits.get("amount") or {}
        cost_limits = limits.get("cost") or {}
        min_qty = safe_float(amount_limits.get("min"), 0.0)
        min_notional = safe_float(cost_limits.get("min"), MIN_NOTIONAL)
        contract_size = safe_float(market_info.get("contractSize"), 1.0) or 1.0

        # USDT value of ONE contract at the current price. Using contractSize is
        # essential: some perps are more than one token per contract, and
        # ignoring it makes the order many times larger than intended.
        unit_value = current_price * contract_size
        if unit_value <= 0:
            print(f"    >>> SKIPPED: {sym} — bad unit value")
            return False

        # Available margin first — leverage is derived to fit it.
        try:
            free_usdt = safe_float(ex_exec.fetch_balance().get("USDT", {}).get("free"), 0.0)
        except Exception:
            free_usdt = 0.0

        # Size so a stop-out loses exactly risk_usdt (4% of capital). No notional
        # cap — the stop distance and the risk budget set the size.
        qty = risk_usdt / (diff * contract_size)
        if min_qty and qty < min_qty:
            qty = min_qty
        if min_notional and qty * unit_value < min_notional:
            qty = min_notional / unit_value

        # Round to the exchange's amount precision — the size actually sent.
        try:
            qty = float(ex_exec.amount_to_precision(sym, qty))
        except Exception:
            qty = round(qty, 6)
        if qty <= 0:
            print(f"    >>> SKIPPED: {sym} — qty rounds to 0")
            return False

        notional = qty * unit_value
        actual_risk = qty * diff * contract_size

        # Leverage needed to afford this notional, within the smaller of the
        # per-trade capital share and 90% of free balance; capped for safety and
        # by the symbol's own maximum.
        budget = min(CAPITAL_USDT / max(1, MAX_TRADES), (free_usdt or CAPITAL_USDT) * 0.90)
        if budget <= 0:
            print(f"    >>> SKIPPED: {sym} — no free margin")
            return False
        sym_max_lev = int(safe_float((limits.get("leverage") or {}).get("max"), LEVERAGE_CAP)) or LEVERAGE_CAP
        leverage = max(1, min(LEVERAGE_CAP, sym_max_lev, math.ceil(notional / budget)))
        required_margin = notional / leverage

        # Guards: never exceed buying power, never place what we can't margin.
        if notional > CAPITAL_USDT * LEVERAGE_CAP * 1.2:
            print(f"    >>> SKIPPED: {sym} — notional ${notional:.2f} beyond max buying power")
            return False
        if free_usdt and required_margin > free_usdt * 0.95:
            print(f"    >>> SKIPPED: {sym} — need ~${required_margin:.2f} margin, only ${free_usdt:.2f} free")
            return False
        print(f"    >>> SIZE: {sym} qty={qty} notional=${notional:.2f} lev={leverage}x "
              f"risk=${actual_risk:.2f} margin~${required_margin:.2f} (free ${free_usdt:.2f})")

        mode_ok, mode_report = _check_symbol_modes(ex_exec, sym)
        if not mode_ok:
            print(f"    >>> MODE CHECK FAILED: {sym} {mode_report.get('error', 'unknown')}")
            log_trade({
                "event": "mode_check_failed",
                "symbol": sym,
                "direction": s["direction"],
                "mode_report": mode_report,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return False

        print(
            f"    >>> MODE CHECK: {sym} position={mode_report['position_mode']} "
            f"margin={mode_report['margin_mode']}"
        )

        actual_stop = float(s["stop"])
        actual_target = float(s["target"])

        tp_payload = {
            "triggerPrice": actual_target,
            "workingType": "MARK_PRICE",
            "type": "TAKE_PROFIT_MARKET",
            "quantity": qty,
        }
        sl_payload = {
            "triggerPrice": actual_stop,
            "workingType": "MARK_PRICE",
            "type": "STOP_MARKET",
            "quantity": qty,
        }

        open_orders = load_open_orders()
        if any(o["symbol"] == sym for o in open_orders):
            print(f"    >>> SKIPPED: {sym} — already has open orders")
            return False

        if len(open_orders) >= MAX_TRADES:
            print(f"    >>> SKIPPED: {sym} — max {MAX_TRADES} trades reached")
            return False

        total_notional = sum(
            o.get("qty", 0) * o.get("entry", 0)
            for o in open_orders
            if o.get("entry", 0) > 0 and o.get("qty", 0) > 0
        ) + notional
        if total_notional > MAX_TOTAL_NOTIONAL:
            print(f"    >>> SKIPPED: {sym} — total notional ${total_notional:.2f} > ${MAX_TOTAL_NOTIONAL}")
            return False

        # One-way mode wants side/positionSide "BOTH"; hedged mode wants LONG/SHORT.
        position_side = s["direction"] if hedged_mode else "BOTH"
        # Cross margin so the set leverage actually reduces the required margin.
        _ensure_margin_mode(ex_exec, sym, "cross")
        if not _ensure_leverage(ex_exec, sym, leverage, position_side):
            return False

        entry_order = ex_exec.create_order(
            sym,
            "market",
            side,
            qty,
            None,
            params={
                "positionSide": position_side,
                "takeProfit": tp_payload,
                "stopLoss": sl_payload,
            },
        )
        if not entry_order or not entry_order.get("id"):
            print(f"    >>> ENTRY FAILED: {sym} — no order ID returned")
            return False

        entry_order_id = entry_order.get("id")
        actual_entry = safe_float(entry_order.get("average"), 0)
        if actual_entry <= 0:
            actual_entry = safe_float(entry_order.get("price"), 0)
        if actual_entry <= 0:
            actual_entry = current_price

        log_trade({"event": "entry", "symbol": sym, "direction": s["direction"],
                   "qty": qty, "entry": actual_entry, "stop": actual_stop,
                   "target": actual_target, "entry_order_id": entry_order_id,
                   "hedged_mode": hedged_mode,
                   "sl_attached": True,
                   "tp_attached": True,
                   "timestamp": datetime.now(timezone.utc).isoformat()})
        print(f"    >>> ENTRY: {sym} {side} {qty} @ {actual_entry} (order={entry_order_id})")
        print(f"    >>> BRACKET: SL @ {actual_stop} | TP @ {actual_target} | hedged={hedged_mode}")

        open_orders.append({
            "symbol": sym,
            "direction": s["direction"],
            "entry": actual_entry,
            "stop": actual_stop,
            "target": actual_target,
            "qty": qty,
            "entry_order_id": entry_order_id,
            "hedged_mode": hedged_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        save_open_orders(open_orders)
        return True

    except Exception as e:
        print(f"    >>> ORDER FAILED: {s['symbol']} {type(e).__name__}: {e}")
        return False


def main():
    print("Connecting to BingX...")
    ex = ccxt.bingx()
    ex.options["defaultType"] = "swap"
    ex.load_markets()
    print(f"Markets loaded: {len(ex.markets)}")

    if os.environ.get("BINGX_EXECUTION_MODE") == "live":
        apikey, apisec = _load_live_credentials()
        if apikey and apisec:
            print("Live mode: BingX credentials detected")
            ex_client = make_authed_client(apikey, apisec)
            cancel_orphaned_orders(ex_client)
            open_orders = load_open_orders()
            if open_orders:
                open_orders = sync_positions_with_exchange(ex_client, open_orders)
                save_open_orders(open_orders)
        else:
            print("Live mode warning: BingX credentials missing or incomplete; orders will be skipped")

    os.makedirs(CACHE_DIR, exist_ok=True)
    to_fetch = _discover_symbols(ex)

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
                sig["market_key"] = ccxt_sym
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
            print(f"\n  {s['symbol']}  {s['direction']:5s}  {s['pattern']}")
            print(f"    Trigger: {s['trigger_ts']}  Close={s['trigger_close']}")
            print(f"    Entry:   {s['entry']:.6f}  Stop={s['stop']:.6f}  Target={s['target']:.6f}")
            print(f"    Risk/unit: {risk:.6f}  Reward/unit: {reward:.6f}  RR=1:{rr:.0f}")
            if 'entry_volume_ratio' in s:
                print(f"    Entry vol: {s['entry_volume_ratio']:.2f}x avg")

    if not signals:
        pass  # already printed "No actionable signals" above
    elif os.environ.get("BINGX_EXECUTION_MODE") != "live":
        print(f"\n  Signals found but not in live mode. Set BINGX_EXECUTION_MODE=live for real orders.")
    else:
        apikey, apisec = _load_live_credentials()
        if not apikey or not apisec:
            print("\n  LIVE mode set but missing BINGX_API_KEY/SECRET_KEY. Skipping orders.")
        else:
            ex_exec = make_authed_client(apikey, apisec)
            hedged_mode = _get_hedged_mode(ex_exec)
            for s in signals:
                place_bracket_order(ex_exec, s, hedged_mode)


if __name__ == "__main__":
    main()
