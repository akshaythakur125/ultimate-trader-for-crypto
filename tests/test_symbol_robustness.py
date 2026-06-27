import pytest
from ultimate_trader.robustness_lab import FrozenConfig
from ultimate_trader.robustness_lab.symbol_robustness import SymbolRobustness, SymbolResult


class TestSymbolRobustness:
    def test_symbol_result_defaults(self):
        sr = SymbolResult(symbol="BTCUSDT", timeframe="15m", candles=100, total_trades=0, win_rate=0, expectancy=0, profit_factor=0, avg_trades_per_day=0, max_drawdown=0)
        assert sr.symbol == "BTCUSDT"
        assert sr.data_available is True
        assert sr.error == ""

    def test_symbol_result_data_available_false(self):
        sr = SymbolResult(symbol="BTCUSDT", timeframe="15m", candles=10, total_trades=0, win_rate=0, expectancy=0, profit_factor=0, avg_trades_per_day=0, max_drawdown=0, data_available=False, error="No data")
        assert sr.data_available is False
        assert sr.error == "No data"

    def test_robustness_init(self):
        frozen = FrozenConfig()
        sr = SymbolRobustness(frozen)
        assert sr.results == []

    def test_empty_run_no_data(self, monkeypatch):
        frozen = FrozenConfig()
        sr = SymbolRobustness(frozen)
        def fake_ensure(*a, **kw):
            return []
        monkeypatch.setattr("ultimate_trader.robustness_lab.symbol_robustness.ensure_data", fake_ensure)
        sr.run(symbols=["UNKNOWNSYMBOL"])
        assert len(sr.results) == 1
        assert sr.results[0].data_available is False
