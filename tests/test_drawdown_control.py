import pytest
from datetime import datetime, timedelta
from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection, ExitReason
from ultimate_trader.drawdown_control.symbol_timeframe_attribution import SymbolTimeframeAttribution


def make_trade(trade_id: str, net_r: float, signal_time: datetime, symbol: str = "BTCUSDT"):
    return ReplayTrade(
        trade_id=trade_id, symbol=symbol, direction=TradeDirection.LONG,
        signal_time=signal_time, gross_r=net_r, fees_r=0, slippage_r=0, funding_r=0,
        net_r=net_r, entry_price=100, exit_price=100 + net_r, stop_loss=99, target_price=110,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
    )


class TestSymbolTimeframeAttribution:
    def test_empty_group(self):
        sta = SymbolTimeframeAttribution()
        r = sta.analyze({})
        assert r == []

    def test_single_group(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(10)]
        sta = SymbolTimeframeAttribution()
        r = sta.analyze({("BTCUSDT", "15m"): trades})
        assert len(r) == 1
        assert r[0].symbol == "BTCUSDT"
        assert r[0].trades == 10

    def test_reliability_insufficient(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(3)]
        sta = SymbolTimeframeAttribution()
        r = sta.analyze({("BTCUSDT", "15m"): trades})
        assert r[0].reliability == "INSUFFICIENT_TRADES"

    def test_reliability_reliable(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i)) for i in range(10)]
        sta = SymbolTimeframeAttribution()
        r = sta.analyze({("BTCUSDT", "15m"): trades})
        assert r[0].reliability == "RELIABLE"

    def test_reliability_dangerous(self):
        t0 = datetime(2024, 1, 1)
        trades = [make_trade(f"t{i}", -1.0, t0 + timedelta(hours=i)) for i in range(10)]
        sta = SymbolTimeframeAttribution()
        r = sta.analyze({("BTCUSDT", "15m"): trades})
        assert r[0].reliability == "DANGEROUS"

    def test_contribution_to_profit(self):
        t0 = datetime(2024, 1, 1)
        btc_trades = [make_trade(f"b{i}", 1.0, t0 + timedelta(hours=i)) for i in range(10)]
        eth_trades = [make_trade(f"e{i}", 0.5, t0 + timedelta(hours=i)) for i in range(10)]
        total_net = sum(t.net_r for t in btc_trades + eth_trades)
        sta = SymbolTimeframeAttribution()
        r = sta.analyze({("BTCUSDT", "15m"): btc_trades, ("ETHUSDT", "15m"): eth_trades},
                        total_net_r=total_net)
        assert r[0].contribution_to_profit > 0
