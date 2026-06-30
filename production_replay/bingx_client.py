"""BingX read-only API connector.

Loads credentials from environment variables only.
No order placement, no cancel, no leverage change, no withdrawal.

Environment variables:
    BINGX_API_KEY         — API key (optional for public data)
    BINGX_API_SECRET      — API secret (optional for public data)
    BINGX_API_BASE_URL    — Base URL (default: https://api.bingx.com)
    BINGX_EXECUTION_MODE  — Must be "read_only" (default)
"""

import hashlib, hmac, json, os, time
from typing import Any
from urllib.parse import urlencode

import requests

DEFAULT_BASE_URL = "https://open-api.bingx.com"
EXECUTION_MODE = os.environ.get("BINGX_EXECUTION_MODE", "read_only").lower()


def load_credentials() -> dict[str, str | None]:
    api_key = os.environ.get("BINGX_API_KEY")
    api_secret = os.environ.get("BINGX_API_SECRET")
    base_url = os.environ.get("BINGX_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    return {"api_key": api_key, "api_secret": api_secret, "base_url": base_url}


def credentials_found(creds: dict | None = None) -> bool:
    if creds is None:
        creds = load_credentials()
    return bool(creds.get("api_key") and creds.get("api_secret"))


def _sign(params: dict[str, str], secret: str) -> str:
    query = urlencode(sorted(params.items()))
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def _public_request(endpoint: str, base_url: str, params: dict | None = None) -> dict[str, Any]:
    url = f"{base_url}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return {"success": True, "data": resp.json(), "error": None}
    except requests.RequestException as e:
        return {"success": False, "data": None, "error": str(e)}


def _signed_request(
    endpoint: str, api_key: str, api_secret: str, base_url: str, params: dict | None = None,
) -> dict[str, Any]:
    if params is None:
        params = {}
    params["timestamp"] = str(int(time.time() * 1000))
    params["signature"] = _sign(params, api_secret)
    headers = {"X-BX-APIKEY": api_key}
    url = f"{base_url}{endpoint}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return {"success": True, "data": resp.json(), "error": None}
    except requests.RequestException as e:
        return {"success": False, "data": None, "error": str(e)}


def get_ticker(symbol: str = "BTC-USDT", base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        base_url = load_credentials()["base_url"]
    return _public_request("/openApi/spot/v1/ticker/price", base_url, {"symbol": symbol})


def get_account_balance(creds: dict | None = None) -> dict[str, Any]:
    if creds is None:
        creds = load_credentials()
    if not credentials_found(creds):
        return {"success": False, "data": None, "error": "API credentials not found"}
    return _signed_request(
        "/openApi/spot/v1/account/balance",
        creds["api_key"], creds["api_secret"], creds["base_url"],
    )


def get_open_positions(creds: dict | None = None) -> dict[str, Any]:
    if creds is None:
        creds = load_credentials()
    if not credentials_found(creds):
        return {"success": False, "data": None, "error": "API credentials not found"}
    return _signed_request(
        "/openApi/swap/v2/user/positions",
        creds["api_key"], creds["api_secret"], creds["base_url"],
    )


def get_klines(symbol: str = "BTC-USDT", interval: str = "15m", limit: int = 100,
               base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        base_url = load_credentials()["base_url"]
    return _public_request(
        "/openApi/swap/v2/quote/klines", base_url,
        {"symbol": symbol, "interval": interval, "limit": str(limit)},
    )


def get_swap_ticker(symbol: str = "BTC-USDT",
                    base_url: str | None = None) -> dict[str, Any]:
    """Fetch 24h ticker data (price, volume, change) for a swap symbol."""
    if base_url is None:
        base_url = load_credentials()["base_url"]
    return _public_request(
        "/openApi/swap/v2/quote/ticker", base_url,
        {"symbol": symbol},
    )


def get_all_swap_tickers(base_url: str | None = None) -> dict[str, Any]:
    """Fetch 24h ticker data for all swap symbols (no params = all)."""
    if base_url is None:
        base_url = load_credentials()["base_url"]
    return _public_request("/openApi/swap/v2/quote/ticker", base_url)
