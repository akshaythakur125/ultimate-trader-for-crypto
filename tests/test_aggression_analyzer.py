from ultimate_trader.orderflow_intelligence.aggression_analyzer import (
    AggressionAnalyzer,
)
from ultimate_trader.orderflow_intelligence.models import (
    AggressionBias,
    FlowWindow,
)


def make_window(
    buy_vol: float = 0.0,
    sell_vol: float = 0.0,
    trade_count: int = 0,
    large_count: int = 0,
) -> FlowWindow:
    return FlowWindow(
        symbol="BTCUSDT",
        total_buy_volume=buy_vol,
        total_sell_volume=sell_vol,
        buy_sell_delta=buy_vol - sell_vol,
        trade_count=trade_count,
        large_trade_count=large_count,
    )


class TestAggressionAnalyzer:
    def test_buyer_dominance(self):
        a = AggressionAnalyzer(aggression_threshold=0.6)
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10)
        r = a.analyze(w)
        assert r.aggression_bias == AggressionBias.BUYER_AGGRESSION
        assert r.buy_aggression_score == 80.0
        assert r.sell_aggression_score == 20.0

    def test_seller_dominance(self):
        a = AggressionAnalyzer(aggression_threshold=0.6)
        w = make_window(buy_vol=30.0, sell_vol=70.0, trade_count=10)
        r = a.analyze(w)
        assert r.aggression_bias == AggressionBias.SELLER_AGGRESSION

    def test_balanced_aggression(self):
        a = AggressionAnalyzer(aggression_threshold=0.6)
        w = make_window(buy_vol=52.0, sell_vol=48.0, trade_count=10)
        r = a.analyze(w)
        assert r.aggression_bias == AggressionBias.BALANCED

    def test_leaning_but_not_dominant(self):
        a = AggressionAnalyzer(aggression_threshold=0.6)
        w = make_window(buy_vol=62.0, sell_vol=38.0, trade_count=10)
        r = a.analyze(w)
        assert r.aggression_bias == AggressionBias.BUYER_AGGRESSION

    def test_empty_window(self):
        a = AggressionAnalyzer()
        w = make_window(trade_count=0)
        r = a.analyze(w)
        assert r.aggression_bias == AggressionBias.UNKNOWN
        assert r.aggression_summary == "No trade data available"

    def test_large_trade_pressure_very_high(self):
        a = AggressionAnalyzer(large_trade_threshold=0.3)
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10, large_count=7)
        r = a.analyze(w)
        assert r.large_trade_pressure == "very_high"

    def test_large_trade_pressure_elevated(self):
        a = AggressionAnalyzer(large_trade_threshold=0.3)
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10, large_count=4)
        r = a.analyze(w)
        assert r.large_trade_pressure == "elevated"

    def test_large_trade_pressure_normal(self):
        a = AggressionAnalyzer(large_trade_threshold=0.3)
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10, large_count=1)
        r = a.analyze(w)
        assert r.large_trade_pressure == "normal"

    def test_summary_contains_bias_and_scores(self):
        a = AggressionAnalyzer()
        w = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=5, large_count=2)
        r = a.analyze(w)
        assert "bias=BUYER_AGGRESSION" in r.aggression_summary
        assert "buy=70%" in r.aggression_summary
        assert "sell=30%" in r.aggression_summary

    def test_summary_includes_pressure_when_elevated(self):
        a = AggressionAnalyzer(large_trade_threshold=0.3)
        w = make_window(buy_vol=60.0, sell_vol=40.0, trade_count=5, large_count=2)
        r = a.analyze(w)
        assert "large_trade_pressure=" in r.aggression_summary

    def test_summary_omits_pressure_when_normal(self):
        a = AggressionAnalyzer(large_trade_threshold=0.3)
        w = make_window(buy_vol=60.0, sell_vol=40.0, trade_count=5, large_count=1)
        r = a.analyze(w)
        assert "large_trade_pressure=" not in r.aggression_summary

    def test_no_trades_has_no_pressure(self):
        a = AggressionAnalyzer()
        w = make_window(trade_count=0)
        r = a.analyze(w)
        assert r.large_trade_pressure == ""

    def test_bias_falls_back_to_ratio_when_below_threshold(self):
        a = AggressionAnalyzer(aggression_threshold=0.8)
        w = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=10)
        r = a.analyze(w)
        assert r.aggression_bias == AggressionBias.BUYER_AGGRESSION

    def test_scores_round_to_two_decimals(self):
        a = AggressionAnalyzer()
        w = make_window(buy_vol=1.0, sell_vol=3.0, trade_count=4)
        r = a.analyze(w)
        assert r.buy_aggression_score == 25.0
        assert r.sell_aggression_score == 75.0
