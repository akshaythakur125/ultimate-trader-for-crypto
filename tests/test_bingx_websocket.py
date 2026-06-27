from unittest.mock import MagicMock, patch

import pytest

from ultimate_trader.bingx.errors import BingXConnectionError
from ultimate_trader.bingx.websocket import BingXWebSocket


class TestBingXWebSocketInit:
    def test_default_initialization(self):
        ws = BingXWebSocket()
        assert ws.ws_url == "wss://ws-api.bingx.com"
        assert ws.api_key is None
        assert ws.secret_key is None
        assert ws.reconnect is True
        assert ws.max_reconnect_attempts == 5

    def test_custom_url(self):
        ws = BingXWebSocket(ws_url="wss://test.bingx.com")
        assert ws.ws_url == "wss://test.bingx.com"


class TestBingXWebSocketHealth:
    def test_health_check_not_connected(self):
        ws = BingXWebSocket()
        assert ws.health_check() is False

    def test_health_check_connected(self):
        ws = BingXWebSocket()
        ws._ws = MagicMock()
        ws._running = True
        assert ws.health_check() is True


class TestBingXWebSocketConnect:
    @patch("ultimate_trader.bingx.websocket.websocket", None)
    def test_connect_no_library(self):
        ws = BingXWebSocket()
        with pytest.raises(BingXConnectionError, match="websocket-client library is not installed"):
            ws.connect()

    @patch("ultimate_trader.bingx.websocket.websocket.WebSocketApp")
    @patch("ultimate_trader.bingx.websocket.threading.Thread")
    def test_connect_success(self, mock_thread, mock_ws_app):
        mock_ws_instance = MagicMock()
        mock_ws_app.return_value = mock_ws_instance
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        ws = BingXWebSocket()
        ws.connect()
        assert ws._ws is not None
        assert ws._running is True
        mock_ws_app.assert_called_once()
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()


class TestBingXWebSocketSubscribe:
    def test_subscribe_klines_not_connected(self):
        ws = BingXWebSocket()
        with pytest.raises(BingXConnectionError):
            ws.subscribe_klines("BTCUSDT")

    def test_subscribe_depth_not_connected(self):
        ws = BingXWebSocket()
        with pytest.raises(BingXConnectionError):
            ws.subscribe_depth("BTCUSDT")

    def test_subscribe_ticker_not_connected(self):
        ws = BingXWebSocket()
        with pytest.raises(BingXConnectionError):
            ws.subscribe_ticker("BTCUSDT")

    def test_subscribe_klines_sends_message(self):
        ws = BingXWebSocket()
        ws._ws = MagicMock()
        ws._running = True
        ws.subscribe_klines("BTCUSDT", "1h")
        ws._ws.send.assert_called_once()
        import json
        sent = json.loads(ws._ws.send.call_args[0][0])
        assert sent["type"] == "subscribe"
        assert "btcusdt@kline_1h" in sent["channel"]

    def test_subscribe_depth_sends_message(self):
        ws = BingXWebSocket()
        ws._ws = MagicMock()
        ws._running = True
        ws.subscribe_depth("ETHUSDT", 50)
        ws._ws.send.assert_called_once()
        import json
        sent = json.loads(ws._ws.send.call_args[0][0])
        assert sent["type"] == "subscribe"
        assert "ethusdt@depth50" in sent["channel"]

    def test_subscribe_ticker_sends_message(self):
        ws = BingXWebSocket()
        ws._ws = MagicMock()
        ws._running = True
        ws.subscribe_ticker("BTCUSDT")
        ws._ws.send.assert_called_once()
        import json
        sent = json.loads(ws._ws.send.call_args[0][0])
        assert sent["type"] == "subscribe"
        assert "btcusdt@ticker" in sent["channel"]


class TestBingXWebSocketCallbacks:
    def test_on_message_callback(self):
        ws = BingXWebSocket()
        callback = MagicMock()
        ws.on("message", callback)
        ws._on_message(None, '{"channel": "test", "data": {"price": 100}}')
        callback.assert_called_once()
        args = callback.call_args[0][0]
        assert args["channel"] == "test"

    def test_on_channel_callback(self):
        ws = BingXWebSocket()
        callback = MagicMock()
        ws.on("btcusdt@ticker", callback)
        ws._on_message(None, '{"channel": "btcusdt@ticker", "data": {"price": 100}}')
        callback.assert_called_once()

    def test_on_open_triggers_callback(self):
        ws = BingXWebSocket()
        callback = MagicMock()
        ws.on("open", callback)
        ws._on_open(None)
        callback.assert_called_once()

    def test_on_error_triggers_callback(self):
        ws = BingXWebSocket()
        callback = MagicMock()
        ws.on("error", callback)
        ws._on_error(None, Exception("test error"))
        callback.assert_called_once()

    def test_on_close_triggers_callback(self):
        ws = BingXWebSocket()
        callback = MagicMock()
        ws.on("close", callback)
        ws._on_close(None, 1000, "Normal closure")
        callback.assert_called_once()


class TestBingXWebSocketDisconnect:
    def test_disconnect_stops_running(self):
        ws = BingXWebSocket()
        mock_ws = MagicMock()
        ws._ws = mock_ws
        ws._running = True
        ws.disconnect()
        assert ws._running is False
        mock_ws.close.assert_called_once()

    def test_disconnect_no_ws(self):
        ws = BingXWebSocket()
        ws.disconnect()
        assert ws._running is False


class TestBingXWebSocketReconnect:
    def test_on_close_triggers_reconnect(self):
        ws = BingXWebSocket()
        ws._ws = MagicMock()
        ws._running = True
        with patch.object(ws, "connect") as mock_connect:
            ws._on_close(None, 1006, "Abnormal closure")
            mock_connect.assert_called_once()

    def test_on_close_max_attempts(self):
        ws = BingXWebSocket(max_reconnect_attempts=2)
        ws._ws = MagicMock()
        ws._running = True
        with patch.object(ws, "connect") as mock_connect:
            ws._reconnect_count = 2
            ws._on_close(None, 1006, "Abnormal closure")
            mock_connect.assert_not_called()
