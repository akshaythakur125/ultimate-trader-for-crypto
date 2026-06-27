from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest
import requests

from ultimate_trader.bingx.client import BingXClient
from ultimate_trader.bingx.errors import (
    BingXAuthError,
    BingXConnectionError,
    BingXDataError,
    BingXNotConfiguredError,
    BingXRateLimitError,
)
from ultimate_trader.bingx.models import Kline, OrderBook, OrderBookLevel, Ticker


class TestBingXClientInit:
    def test_default_initialization(self):
        client = BingXClient()
        assert client.base_url == "https://api.bingx.com"
        assert client.api_key is None
        assert client.secret_key is None
        assert client.timeout == 30

    def test_custom_base_url(self):
        client = BingXClient(base_url="https://test.bingx.com/")
        assert client.base_url == "https://test.bingx.com"


class TestBingXClientHealth:
    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_health_check_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "symbol": "BTCUSDT",
            "lastPrice": "50000.0",
            "priceChangePercent": "1.5",
            "highPrice": "51000.0",
            "lowPrice": "49000.0",
            "volume": "1000.0",
            "quoteVolume": "50000000.0",
        }
        mock_get.return_value = mock_resp
        client = BingXClient()
        assert client.health_check() is True

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_health_check_failure(self, mock_get):
        mock_get.side_effect = requests.RequestException("Connection failed")
        client = BingXClient()
        assert client.health_check() is False

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_health_check_no_creds(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"msg": "API key invalid"}
        mock_get.return_value = mock_resp
        client = BingXClient()
        assert client.health_check() is False


class TestBingXClientGetTicker:
    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_ticker_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "symbol": "BTCUSDT",
            "lastPrice": "50000.0",
            "priceChangePercent": "1.5",
            "highPrice": "51000.0",
            "lowPrice": "49000.0",
            "volume": "1000.0",
            "quoteVolume": "50000000.0",
        }
        mock_get.return_value = mock_resp
        client = BingXClient()
        ticker = client.get_ticker("BTCUSDT")
        assert isinstance(ticker, Ticker)
        assert ticker.symbol == "BTCUSDT"
        assert ticker.last_price == 50000.0
        assert ticker.price_change_percent == 1.5
        assert ticker.high_price == 51000.0
        assert ticker.low_price == 49000.0
        assert ticker.volume == 1000.0
        assert ticker.quote_volume == 50000000.0

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_ticker_rate_limit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp
        client = BingXClient()
        with pytest.raises(BingXRateLimitError):
            client.get_ticker("BTCUSDT")

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_ticker_auth_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"msg": "Invalid API key"}
        mock_get.return_value = mock_resp
        client = BingXClient()
        with pytest.raises(BingXAuthError):
            client.get_ticker("BTCUSDT")

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_ticker_connection_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Network error")
        client = BingXClient()
        with pytest.raises(BingXConnectionError):
            client.get_ticker("BTCUSDT")

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_ticker_invalid_json(self, mock_get):
        import json
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_get.return_value = mock_resp
        client = BingXClient()
        with pytest.raises(BingXDataError):
            client.get_ticker("BTCUSDT")


class TestBingXClientGetKlines:
    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_klines_dict_format(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "openTime": 1700000000000,
                "open": "100.0",
                "high": "110.0",
                "low": "99.0",
                "close": "105.0",
                "volume": "1000.0",
                "closeTime": 1700003600000,
                "quoteVolume": "105000.0",
                "tradeCount": 250,
            }
        ]
        mock_get.return_value = mock_resp
        client = BingXClient()
        klines = client.get_klines("BTCUSDT", "1h", limit=1)
        assert len(klines) == 1
        kline = klines[0]
        assert isinstance(kline, Kline)
        assert kline.symbol == "BTCUSDT"
        assert kline.interval == "1h"
        assert kline.open_price == 100.0
        assert kline.high_price == 110.0
        assert kline.low_price == 99.0
        assert kline.close_price == 105.0
        assert kline.volume == 1000.0
        assert kline.trade_count == 250

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_klines_list_format(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            [1700000000000, "100.0", "110.0", "99.0", "105.0", "1000.0", 1700003600000, "105000.0", 250]
        ]
        mock_get.return_value = mock_resp
        client = BingXClient()
        klines = client.get_klines("ETHUSDT", "15m", limit=1)
        assert len(klines) == 1
        assert klines[0].symbol == "ETHUSDT"
        assert klines[0].close_price == 105.0

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_klines_limit_capped(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp
        client = BingXClient()
        client.get_klines("BTCUSDT", limit=5000)
        call_params = mock_get.call_args[1]["params"]
        assert call_params["limit"] == 1000


class TestBingXClientGetOrderBook:
    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_order_book_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "bids": [["100.0", "1.5"], ["99.5", "2.0"]],
            "asks": [["101.0", "1.0"], ["101.5", "1.5"]],
            "lastUpdateId": 12345,
        }
        mock_get.return_value = mock_resp
        client = BingXClient()
        ob = client.get_order_book("BTCUSDT")
        assert isinstance(ob, OrderBook)
        assert ob.symbol == "BTCUSDT"
        assert len(ob.bids) == 2
        assert len(ob.asks) == 2
        assert ob.bids[0].price == 100.0
        assert ob.bids[0].quantity == 1.5
        assert ob.asks[1].price == 101.5
        assert ob.last_update_id == 12345

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_order_book_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"bids": [], "asks": []}
        mock_get.return_value = mock_resp
        client = BingXClient()
        ob = client.get_order_book("BTCUSDT")
        assert len(ob.bids) == 0
        assert len(ob.asks) == 0

    @patch("ultimate_trader.bingx.client.requests.Session.get")
    def test_get_order_book_limit_capped(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"bids": [], "asks": []}
        mock_get.return_value = mock_resp
        client = BingXClient()
        client.get_order_book("BTCUSDT", limit=500)
        call_params = mock_get.call_args[1]["params"]
        assert call_params["limit"] == 100


class TestBingXClientSigned:
    @patch("ultimate_trader.bingx.client.requests.Session.post")
    def test_signed_post_no_creds(self, mock_post):
        client = BingXClient()
        with pytest.raises(BingXNotConfiguredError):
            client._signed_post("/test", {})

    @patch("ultimate_trader.bingx.client.requests.Session.post")
    def test_signed_post_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True}
        mock_post.return_value = mock_resp
        client = BingXClient(api_key="test_key", secret_key="test_secret")
        result = client._signed_post("/test", {"param": "value"})
        assert result == {"success": True}


class TestBingXClientClose:
    @patch("ultimate_trader.bingx.client.requests.Session.close")
    def test_close(self, mock_close):
        client = BingXClient()
        client.close()
        mock_close.assert_called_once()
