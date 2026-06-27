from ultimate_trader.orderflow_intelligence.absorption_intelligence import (
    AbsorptionIntelligence,
)
from ultimate_trader.orderflow_intelligence.models import (
    AbsorptionState,
    AggressionBias,
    FlowWindow,
)


def make_window(
    buy_vol: float = 0.0,
    sell_vol: float = 0.0,
    trade_count: int = 0,
) -> FlowWindow:
    return FlowWindow(
        symbol="BTCUSDT",
        total_buy_volume=buy_vol,
        total_sell_volume=sell_vol,
        buy_sell_delta=buy_vol - sell_vol,
        trade_count=trade_count,
    )


class TestAbsorptionIntelligence:
    def test_buying_absorbed_detected(self):
        d = AbsorptionIntelligence(absorption_ratio_threshold=0.65, price_stuck_threshold=0.1)
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, price_change_percent=0.05)
        assert r.absorption_detected is True
        assert r.absorption_type == AbsorptionState.BUYING_ABSORBED
        assert r.absorbed_side == "buyers"
        assert r.likely_passive_participant == "institutional_seller"

    def test_selling_absorbed_detected(self):
        d = AbsorptionIntelligence()
        w = make_window(buy_vol=20.0, sell_vol=80.0, trade_count=10)
        r = d.analyze(w, AggressionBias.SELLER_AGGRESSION, price_change_percent=0.05)
        assert r.absorption_detected is True
        assert r.absorption_type == AbsorptionState.SELLING_ABSORBED
        assert r.absorbed_side == "sellers"
        assert r.likely_passive_participant == "institutional_buyer"

    def test_no_absorption_when_price_moves(self):
        d = AbsorptionIntelligence()
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, price_change_percent=0.5)
        assert r.absorption_detected is False

    def test_no_absorption_when_ratio_below_threshold(self):
        d = AbsorptionIntelligence(absorption_ratio_threshold=0.65)
        w = make_window(buy_vol=55.0, sell_vol=45.0, trade_count=10)
        r = d.analyze(w, AggressionBias.BALANCED, price_change_percent=0.05)
        assert r.absorption_detected is False

    def test_insufficient_trades(self):
        d = AbsorptionIntelligence()
        w = make_window(buy_vol=10.0, sell_vol=5.0, trade_count=2)
        r = d.analyze(w, AggressionBias.BALANCED)
        assert r.absorption_detected is False
        assert "Insufficient" in r.absorption_summary

    def test_no_volume(self):
        d = AbsorptionIntelligence()
        w = make_window(trade_count=5)
        r = d.analyze(w, AggressionBias.BALANCED)
        assert r.absorption_detected is False
        assert "No volume" in r.absorption_summary

    def test_absorption_score_matches_ratio(self):
        d = AbsorptionIntelligence()
        w = make_window(buy_vol=90.0, sell_vol=10.0, trade_count=10)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, price_change_percent=0.05)
        assert r.absorption_score == 90.0

    def test_reset_clears_history(self):
        d = AbsorptionIntelligence()
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=5)
        d.analyze(w, AggressionBias.BUYER_AGGRESSION, price_change_percent=0.05)
        d.reset()
        assert len(d._history) == 0

    def test_history_capped_at_twenty(self):
        d = AbsorptionIntelligence()
        for _ in range(25):
            d.analyze(make_window(buy_vol=50.0, sell_vol=50.0, trade_count=5), AggressionBias.BALANCED)
        assert len(d._history) <= 20

    def test_buying_absorbed_summary(self):
        d = AbsorptionIntelligence()
        w = make_window(buy_vol=75.0, sell_vol=25.0, trade_count=10)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, price_change_percent=0.05)
        assert "75%" in r.absorption_summary

    def test_selling_absorbed_summary(self):
        d = AbsorptionIntelligence()
        w = make_window(buy_vol=25.0, sell_vol=75.0, trade_count=10)
        r = d.analyze(w, AggressionBias.SELLER_AGGRESSION, price_change_percent=0.05)
        assert "75%" in r.absorption_summary
