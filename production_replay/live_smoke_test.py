"""Read-only BingX live-trading smoke test.

This script never places, cancels, or closes a real order.
It only validates that the live client can load markets, resolve a symbol,
inspect margin/position mode, and build a plausible one-shot order plan.
"""

import argparse
import json
import os
import sys

import ccxt

from production_replay.live_scan import (
    MAX_NOTIONAL_PER_TRADE,
    MIN_NOTIONAL,
    _check_symbol_modes,
    _load_live_credentials,
    _resolve_market_key,
    safe_float,
)


def _make_smoke_report(ex_client, symbol: str, side: str, notional: float) -> dict:
    market_key = _resolve_market_key(symbol, ex_client.markets) or symbol
    market = ex_client.markets.get(market_key, {})
    ticker = ex_client.fetch_ticker(market_key)
    price = safe_float(
        ticker.get("last")
        or ticker.get("close")
        or ticker.get("bid")
        or ticker.get("ask"),
        0.0,
    )
    if price <= 0:
        return {"ok": False, "symbol": symbol, "market_key": market_key, "error": "no live price"}

    mode_ok, mode_report = _check_symbol_modes(ex_client, market_key)
    qty = round(min(notional, MAX_NOTIONAL_PER_TRADE) / price, 4)
    min_qty = safe_float(market.get("limits", {}).get("amount", {}).get("min"), 0.001)
    min_notional = safe_float(market.get("limits", {}).get("cost", {}).get("min"), MIN_NOTIONAL)
    if qty < min_qty:
        qty = min_qty

    entry_price = price
    stop_price = price * (0.99 if side == "LONG" else 1.01)
    target_price = price * (1.01 if side == "LONG" else 0.99)

    return {
        "ok": bool(mode_ok),
        "mode_report": mode_report,
        "symbol": symbol,
        "market_key": market_key,
        "side": side,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "qty": qty,
        "requested_notional": notional,
        "effective_notional": round(qty * price, 6),
        "min_notional": min_notional,
        "would_place_order": False,
        "would_close_order": False,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only BingX live-trading smoke test.")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="BingX swap symbol to validate")
    parser.add_argument("--side", choices=("LONG", "SHORT"), default="LONG", help="Synthetic side to plan")
    parser.add_argument("--notional", type=float, default=5.0, help="Requested notional for the simulated order")
    args = parser.parse_args(argv)

    api_key, api_secret = _load_live_credentials()
    if not api_key or not api_secret:
        print("Smoke test failed: missing BINGX_API_KEY/BINGX_API_SECRET")
        return 1

    ex = ccxt.bingx({"apiKey": api_key, "secret": api_secret})
    ex.load_markets()
    report = _make_smoke_report(ex, args.symbol, args.side, args.notional)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
