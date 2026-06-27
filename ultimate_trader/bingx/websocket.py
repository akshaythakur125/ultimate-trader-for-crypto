import json
import threading
from typing import Any, Callable, Optional

from ultimate_trader.bingx.errors import BingXConnectionError, BingXNotConfiguredError

try:
    import websocket
except ImportError:
    websocket = None


class BingXWebSocket:
    WS_URL = "wss://ws-api.bingx.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        ws_url: str = WS_URL,
        reconnect: bool = True,
        max_reconnect_attempts: int = 5,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.ws_url = ws_url
        self.reconnect = reconnect
        self.max_reconnect_attempts = max_reconnect_attempts
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._callbacks: dict[str, list[Callable]] = {}
        self._running = False
        self._reconnect_count = 0

    def health_check(self) -> bool:
        return self._ws is not None and self._running

    def connect(self):
        if websocket is None:
            raise BingXConnectionError("websocket-client library is not installed")
        self._running = True
        self._ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._thread.start()

    def subscribe_klines(self, symbol: str, interval: str = "1h"):
        if not self._ws or not self._running:
            raise BingXConnectionError("WebSocket is not connected")
        msg = {
            "type": "subscribe",
            "channel": f"{symbol.lower()}@kline_{interval}",
        }
        self._ws.send(json.dumps(msg))

    def subscribe_depth(self, symbol: str, limit: int = 50):
        if not self._ws or not self._running:
            raise BingXConnectionError("WebSocket is not connected")
        msg = {
            "type": "subscribe",
            "channel": f"{symbol.lower()}@depth{limit}",
        }
        self._ws.send(json.dumps(msg))

    def subscribe_ticker(self, symbol: str):
        if not self._ws or not self._running:
            raise BingXConnectionError("WebSocket is not connected")
        msg = {
            "type": "subscribe",
            "channel": f"{symbol.lower()}@ticker",
        }
        self._ws.send(json.dumps(msg))

    def on(self, event: str, callback: Callable[[dict[str, Any]], None]):
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def disconnect(self):
        self._running = False
        if self._ws:
            self._ws.close()
            self._ws = None
        if self._thread:
            self._thread = None

    def _on_open(self, ws):
        self._reconnect_count = 0
        self._trigger("open", {})

    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        channel = data.get("channel", "unknown")
        self._trigger(channel, data)
        self._trigger("message", data)

    def _on_error(self, ws, error):
        self._trigger("error", {"error": str(error)})

    def _on_close(self, ws, close_status_code, close_msg):
        self._trigger("close", {"code": close_status_code, "message": close_msg})
        if self._running and self.reconnect and self._reconnect_count < self.max_reconnect_attempts:
            self._reconnect_count += 1
            self.connect()

    def _trigger(self, event: str, data: dict[str, Any]):
        for cb in self._callbacks.get(event, []):
            try:
                cb(data)
            except Exception:
                pass
