from production_replay.live_smoke_test import _make_smoke_report


class _FakeBingX:
    def __init__(self):
        self.markets = {
            "BTC/USDT:USDT": {
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 5.0}},
            }
        }

    def fetch_ticker(self, symbol):
        assert symbol == "BTC/USDT:USDT"
        return {"last": 100.0}

    def fetch_position_mode(self, symbol):
        assert symbol == "BTC/USDT:USDT"
        return {"hedged": True}

    def fetch_margin_mode(self, symbol):
        assert symbol == "BTC/USDT:USDT"
        return {"marginMode": "isolated"}


def test_live_smoke_report_is_read_only():
    report = _make_smoke_report(_FakeBingX(), "BTC/USDT:USDT", "LONG", 5.0)

    assert report["ok"] is True
    assert report["would_place_order"] is False
    assert report["would_close_order"] is False
    assert report["qty"] > 0
    assert report["entry_price"] == 100.0
    assert report["mode_report"]["ok"] is True


def test_live_smoke_report_handles_missing_limits():
    class _NoLimitsBingX(_FakeBingX):
        def __init__(self):
            self.markets = {"BTC/USDT:USDT": {"limits": None}}

    report = _make_smoke_report(_NoLimitsBingX(), "BTC/USDT:USDT", "LONG", 5.0)

    assert report["ok"] is True
    assert report["min_notional"] == 5.0
    assert report["qty"] > 0
