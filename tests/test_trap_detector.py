from ultimate_trader.orderflow_intelligence.models import (
    AbsorptionState,
    AggressionBias,
    FlowWindow,
    TrapAction,
    TrapRisk,
)
from ultimate_trader.orderflow_intelligence.trap_detector import TrapDetector


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


class TestTrapDetector:
    def test_long_trap_buying_into_absorption(self):
        d = TrapDetector()
        w = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=10, large_count=1)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.BUYING_ABSORBED, "BEARISH_DIVERGENCE")
        assert r.trap_detected is True
        assert r.trap_type == TrapRisk.LONG_TRAP_RISK
        assert "Long trap" in r.trap_reason

    def test_short_trap_selling_into_absorption(self):
        d = TrapDetector()
        w = make_window(buy_vol=30.0, sell_vol=70.0, trade_count=10, large_count=1)
        r = d.analyze(w, AggressionBias.SELLER_AGGRESSION, AbsorptionState.SELLING_ABSORBED, "BULLISH_DIVERGENCE")
        assert r.trap_detected is True
        assert r.trap_type == TrapRisk.SHORT_TRAP_RISK
        assert "Short trap" in r.trap_reason

    def test_no_trap_when_no_signals(self):
        d = TrapDetector()
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=5)
        r = d.analyze(w, AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, "NO_DIVERGENCE")
        assert r.trap_detected is False
        assert r.trap_type == TrapRisk.LOW_TRAP_RISK
        assert r.recommended_action == TrapAction.WAIT

    def test_trap_detected_with_divergence_and_weak_breakdown(self):
        d = TrapDetector()
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10, large_count=1)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.SELLING_ABSORBED, "BULLISH_DIVERGENCE")
        assert r.trap_detected is True
        assert r.recommended_action in (TrapAction.CAUTION, TrapAction.BLOCK_TRADE)

    def test_block_trade_when_score_high(self):
        d = TrapDetector()
        w = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=26, large_count=6)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.BUYING_ABSORBED, "BEARISH_DIVERGENCE")
        assert r.recommended_action in (TrapAction.CAUTION, TrapAction.BLOCK_TRADE)
        assert r.trap_score > 60

    def test_caution_when_score_moderate(self):
        d = TrapDetector()
        w = make_window(buy_vol=60.0, sell_vol=40.0, trade_count=5, large_count=1)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.BUYING_ABSORBED, "BEARISH_DIVERGENCE")
        assert r.recommended_action in (TrapAction.CAUTION, TrapAction.BLOCK_TRADE)

    def test_long_trap_requires_minimum_two_signals(self):
        d = TrapDetector()
        w = make_window(buy_vol=55.0, sell_vol=45.0, trade_count=5)
        r = d.analyze(w, AggressionBias.BALANCED, AbsorptionState.BUYING_ABSORBED, "NO_DIVERGENCE")
        assert r.trap_detected is False

    def test_short_trap_requires_minimum_two_signals(self):
        d = TrapDetector()
        w = make_window(buy_vol=45.0, sell_vol=55.0, trade_count=5)
        r = d.analyze(w, AggressionBias.BALANCED, AbsorptionState.SELLING_ABSORBED, "NO_DIVERGENCE")
        assert r.trap_detected is False

    def test_reset(self):
        d = TrapDetector()
        d.analyze(make_window(trade_count=5), AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, "NO_DIVERGENCE")
        d.reset()
        assert len(d._history) == 0

    def test_weak_breakout_contributes_to_long_trap(self):
        d = TrapDetector()
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=5, large_count=1)
        r = d.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.BUYING_ABSORBED, "NO_DIVERGENCE")
        assert r.trap_detected is True

    def test_weak_breakdown_contributes_to_short_trap(self):
        d = TrapDetector()
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=5, large_count=1)
        r = d.analyze(w, AggressionBias.SELLER_AGGRESSION, AbsorptionState.SELLING_ABSORBED, "NO_DIVERGENCE")
        assert r.trap_detected is True
