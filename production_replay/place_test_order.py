"""Force ONE real BingX order through the live bb v1 order path — on demand.

Why this exists: bb v1 signals (3.5-sigma band breaks + volume) are rare, so a
scan can run for hours with zero signals and never exercise the order code.
This tool builds a synthetic signal at the current market price for one symbol
and routes it through live_scan.place_bracket_order — the identical function a
real signal uses. It proves real orders land end-to-end without waiting.

It respects the same caps as the live scanner ($1 risk, $5 notional/trade,
$10 total, max 3 open, 2x leverage) and attaches a real stop-loss and
take-profit. It places at most ONE order.

SAFETY: prints the plan and does nothing unless you pass --confirm. Requires
BINGX_API_KEY / BINGX_API_SECRET in the environment. BINGX_EXECUTION_MODE is
NOT required here — passing --confirm IS your explicit go-ahead.

Usage:
    # preview only (no order):
    python -m production_replay.place_test_order --symbol BTC/USDT:USDT --side LONG
    # actually place the real order:
    python -m production_replay.place_test_order --symbol BTC/USDT:USDT --side LONG --confirm
"""

import argparse
import sys

from production_replay.live_scan import (
    RISK_PCT,
    BB_RR_TARGET,
    _get_hedged_mode,
    _load_live_credentials,
    _resolve_market_key,
    make_authed_client,
    place_bracket_order,
    safe_float,
)


def _build_signal(ex, symbol: str, side: str) -> dict | None:
    market_key = _resolve_market_key(symbol, ex.markets) or symbol
    if market_key not in ex.markets:
        print(f"Symbol not found on BingX: {symbol}")
        return None
    ticker = ex.fetch_ticker(market_key)
    price = safe_float(ticker.get("last") or ticker.get("close")
                       or ticker.get("bid") or ticker.get("ask"), 0.0)
    if price <= 0:
        print(f"No live price for {market_key}")
        return None

    # Same bracket geometry as detect_bb_bounce: 0.5% stop, 5% target (RR 10).
    if side == "LONG":
        stop = price * (1 - RISK_PCT)
        target = price * (1 + RISK_PCT * BB_RR_TARGET)
    else:
        stop = price * (1 + RISK_PCT)
        target = price * (1 - RISK_PCT * BB_RR_TARGET)

    return {
        "symbol": symbol.replace("/", "_").replace(":USDT", ""),
        "market_key": market_key,
        "direction": side,
        "entry": price,
        "stop": stop,
        "target": target,
        "current_price": price,
        "pattern": "manual_test_order",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Place ONE real test order via the live bb v1 path.")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="BingX swap symbol")
    parser.add_argument("--side", choices=("LONG", "SHORT"), default="LONG")
    parser.add_argument("--confirm", action="store_true",
                        help="Actually place the real order (omit for a dry preview)")
    args = parser.parse_args(argv)

    api_key, api_secret = _load_live_credentials()
    if not api_key or not api_secret:
        print("Missing BINGX_API_KEY / BINGX_API_SECRET in environment.")
        return 1

    ex = make_authed_client(api_key, api_secret)

    sig = _build_signal(ex, args.symbol, args.side)
    if not sig:
        return 1

    risk = abs(sig["entry"] - sig["stop"])
    print("=" * 60)
    print("  MANUAL TEST ORDER — bb v1 live path")
    print("=" * 60)
    print(f"  Symbol:   {sig['market_key']}")
    print(f"  Side:     {sig['direction']}")
    print(f"  Entry~:   {sig['entry']:.6f}  (market)")
    print(f"  Stop:     {sig['stop']:.6f}")
    print(f"  Target:   {sig['target']:.6f}")
    print(f"  Risk/unit:{risk:.6f}  (real order — sized to the strategy's risk budget)")
    print("=" * 60)

    if not args.confirm:
        print("\n  DRY PREVIEW — no order placed. Re-run with --confirm to place it.")
        return 0

    hedged_mode = _get_hedged_mode(ex)
    print(f"\n  Placing real order (hedged_mode={hedged_mode})...\n")
    placed = place_bracket_order(ex, sig, hedged_mode)
    if placed:
        print("\n  RESULT: ORDER PLACED. Check BingX for the position + attached SL/TP.")
        return 0
    print("\n  RESULT: order NOT placed — see the reason above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
