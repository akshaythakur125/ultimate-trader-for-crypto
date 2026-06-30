"""BingX read-only connector healthcheck.

Usage:
    python -m production_replay.bingx_healthcheck
"""

import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import (
    load_credentials, credentials_found,
    get_ticker, get_account_balance, get_open_positions,
    EXECUTION_MODE,
)


def main():
    creds = load_credentials()
    has_creds = credentials_found(creds)

    print("=" * 60)
    print("  BINGX READ-ONLY CONNECTOR — HEALTHCHECK")
    print("=" * 60)
    print(f"  Credentials found:  {'YES' if has_creds else 'NO'}")
    print(f"  API Key present:    {'YES' if creds.get('api_key') else 'NO'}")
    print(f"  Base URL:           {creds.get('base_url', 'N/A')}")
    print(f"  Execution mode:     {EXECUTION_MODE}")
    print(f"  Trading enabled:    NO")
    print(f"  Order placement:    NO")
    print()

    # Public market data
    print("  Testing public market data (BTC-USDT)...")
    ticker = get_ticker("BTC-USDT", creds["base_url"])
    if ticker["success"] and ticker["data"]:
        print(f"    Public market data: REACHABLE")
        data = ticker["data"]
        code = data.get("code") if isinstance(data, dict) else None
        if code == 0:
            inner = data.get("data", [])
            if isinstance(inner, list) and inner:
                print(f"    BTC ticker:         {inner[0].get('symbol', 'N/A')}")
            elif isinstance(inner, dict):
                print(f"    BTC price:          {inner.get('price', 'N/A')}")
            else:
                print(f"    Response code:      0")
        else:
            print(f"    Response:           {str(data)[:100]}")
        print(f"    Public market reachable: YES")
    else:
        print(f"    Public market reachable: NO ({ticker.get('error', 'unknown')})")
    print()

    # Account balance (only if keys exist)
    if has_creds:
        print("  Testing account balance...")
        balances = get_account_balance(creds)
        if balances["success"]:
            print(f"    Account read:       REACHABLE")
            print(f"    Account reachable:  YES")
        else:
            print(f"    Account read:       NOT REACHABLE ({balances.get('error', 'unknown')})")
            print(f"    Account reachable:  NO")
        print()

        print("  Testing open positions...")
        positions = get_open_positions(creds)
        if positions["success"]:
            print(f"    Open positions:     REACHABLE")
            print(f"    Positions reachable: YES")
        else:
            print(f"    Open positions:     NOT REACHABLE ({positions.get('error', 'unknown')})")
            print(f"    Positions reachable: NO")
        print()
    else:
        print("  Account/positions: SKIPPED (no API keys)")
        print()

    print("=" * 60)
    print(f"  Overall: {'READY' if has_creds else 'PUBLIC-ONLY'}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
