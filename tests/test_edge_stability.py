import pytest
from ultimate_trader.robustness_lab import FrozenConfig
from ultimate_trader.robustness_lab.edge_stability import EdgeStabilityAnalyzer, EdgeClassification


class TestEdgeStability:
    def test_classify_insufficient_trades(self):
        ana = EdgeStabilityAnalyzer()
        ec = ana.classify([], [], [], [], 5)
        assert ec.verdict == "INSUFFICIENT_TRADES"
        assert "5" in ec.reason

    def test_classify_no_edge_negative_ev(self):
        ana = EdgeStabilityAnalyzer()
        class NegPeriod:
            total_trades = 50
            expectancy = -0.1
            profit_factor = 0.8
            max_drawdown = 1.5
        ec = ana.classify([NegPeriod()], [], [], [], 200)
        assert ec.verdict == "NO_EDGE"

    def test_classify_promising_low_sample(self):
        ana = EdgeStabilityAnalyzer()
        mock_results = [
            MockPeriodResult(30, 0.5, 1.5, 0.5),
        ]
        ec = ana.classify(mock_results, [], [], [], 50)
        assert ec.verdict == "PROMISING_BUT_UNPROVEN"

    def test_classify_robust_edge(self):
        ana = EdgeStabilityAnalyzer()
        periods = [MockPeriodResult(30, 0.6, 2.5, 0.8) for _ in range(3)]
        symbols = [MockSymbolResult(True, 20, 0.7, 2.0, 0.5) for _ in range(3)]
        tfs = [MockTimeResult(True, 15, 0.5, 2.0, 0.3) for _ in range(2)]
        wf_windows = [MockWFWindow(5, 0.6, 2.0) for _ in range(4)]
        ec = ana.classify(periods, symbols, tfs, wf_windows, 300)
        assert ec.verdict == "ROBUST_EDGE"

    def test_edge_classification_defaults(self):
        ec = EdgeClassification()
        assert ec.verdict == "INSUFFICIENT_TRADES"
        assert ec.total_out_of_sample_trades == 0

    def test_edge_classification_custom(self):
        ec = EdgeClassification(verdict="ROBUST_EDGE", total_out_of_sample_trades=500, avg_expectancy=0.75)
        assert ec.verdict == "ROBUST_EDGE"
        assert ec.total_out_of_sample_trades == 500


class MockPeriodResult:
    def __init__(self, total_trades, expectancy, profit_factor, max_drawdown):
        self.total_trades = total_trades
        self.expectancy = expectancy
        self.profit_factor = profit_factor
        self.max_drawdown = max_drawdown

class MockSymbolResult:
    def __init__(self, data_available, total_trades, expectancy, profit_factor, max_drawdown):
        self.data_available = data_available
        self.total_trades = total_trades
        self.expectancy = expectancy
        self.profit_factor = profit_factor
        self.max_drawdown = max_drawdown

class MockTimeResult:
    def __init__(self, data_available, total_trades, expectancy, profit_factor, max_drawdown):
        self.data_available = data_available
        self.total_trades = total_trades
        self.expectancy = expectancy
        self.profit_factor = profit_factor
        self.max_drawdown = max_drawdown

class MockWFWindow:
    def __init__(self, test_trades, test_expectancy, test_profit_factor):
        self.test_trades = test_trades
        self.test_expectancy = test_expectancy
        self.test_profit_factor = test_profit_factor
        self.profitable = test_expectancy > 0
