import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import urlencode

import requests

from ultimate_trader.bingx.errors import (
    BingXAuthError,
    BingXConnectionError,
    BingXDataError,
    BingXNotConfiguredError,
    BingXRateLimitError,
)
from ultimate_trader.bingx.models import Kline, OrderBook, OrderBookLevel, Ticker


class BingXClient:
    BASE_URL = "https://api.bingx.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def health_check(self) -> bool:
        try:
            ticker = self.get_ticker("BTCUSDT")
            return ticker.last_price > 0
        except (BingXConnectionError, BingXDataError, BingXNotConfiguredError, BingXAuthError):
            return False

    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[Kline]:
        params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        data = self._public_get("/openApi/swap/v3/quote/klines", params)
        return self._parse_klines(symbol, interval, data)

    def get_ticker(self, symbol: str) -> Ticker:
        data = self._public_get("/openApi/swap/v3/quote/ticker", {"symbol": symbol})
        return Ticker(
            symbol=data.get("symbol", symbol),
            last_price=float(data.get("lastPrice", 0)),
            price_change_percent=float(data.get("priceChangePercent", 0)),
            high_price=float(data.get("highPrice", 0)),
            low_price=float(data.get("lowPrice", 0)),
            volume=float(data.get("volume", 0)),
            quote_volume=float(data.get("quoteVolume", 0)),
        )

    def get_order_book(self, symbol: str, limit: int = 50) -> OrderBook:
        data = self._public_get(
            "/openApi/swap/v3/quote/depth", {"symbol": symbol, "limit": min(limit, 100)}
        )
        bids = [OrderBookLevel(price=float(b[0]), quantity=float(b[1])) for b in data.get("bids", [])]
        asks = [OrderBookLevel(price=float(a[0]), quantity=float(a[1])) for a in data.get("asks", [])]
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            last_update_id=data.get("lastUpdateId"),
        )

    def _public_get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            raise BingXConnectionError(f"Connection failed: {e}") from e
        return self._handle_response(resp)

    def _signed_post(self, path: str, params: dict) -> dict:
        if not self.api_key or not self.secret_key:
            raise BingXNotConfiguredError("BingX API key and secret key are required")
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(sorted(params.items()))
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        headers = {"X-BX-APIKEY": self.api_key}
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.post(url, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise BingXConnectionError(f"Connection failed: {e}") from e
        return self._handle_response(resp)

    def _handle_response(self, resp: requests.Response) -> dict:
        if resp.status_code == 429:
            raise BingXRateLimitError("Rate limit exceeded")
        if resp.status_code == 403:
            raise BingXAuthError("Authentication failed")
        if resp.status_code >= 500:
            raise BingXConnectionError(f"Server error: {resp.status_code}")
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise BingXDataError(f"Invalid JSON: {e}") from e
        if resp.status_code >= 400:
            msg = data.get("msg", data.get("error", str(data)))
            if "signature" in str(data).lower() or "api" in str(data).lower():
                raise BingXAuthError(f"API error: {msg}")
            raise BingXDataError(f"Request failed: {msg}")
        return data

    def _parse_klines(self, symbol: str, interval: str, data: list) -> list[Kline]:
        from datetime import datetime, timezone

        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(
                    Kline(
                        symbol=symbol,
                        interval=interval,
                        open_time=datetime.fromtimestamp(item["openTime"] / 1000, tz=timezone.utc),
                        open_price=float(item["open"]),
                        high_price=float(item["high"]),
                        low_price=float(item["low"]),
                        close_price=float(item["close"]),
                        volume=float(item["volume"]),
                        close_time=datetime.fromtimestamp(item["closeTime"] / 1000, tz=timezone.utc),
                        quote_volume=float(item.get("quoteVolume", 0)),
                        trade_count=int(item.get("tradeCount", 0)),
                    )
                )
            elif isinstance(item, list) and len(item) >= 9:
                result.append(
                    Kline(
                        symbol=symbol,
                        interval=interval,
                        open_time=datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc),
                        open_price=float(item[1]),
                        high_price=float(item[2]),
                        low_price=float(item[3]),
                        close_price=float(item[4]),
                        volume=float(item[5]),
                        close_time=datetime.fromtimestamp(item[6] / 1000, tz=timezone.utc),
                        quote_volume=float(item[7]),
                        trade_count=int(item[8]),
                    )
                )
        return result

    def close(self):
        self._session.close()
