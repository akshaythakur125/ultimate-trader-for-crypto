from ultimate_trader.orderflow_intelligence.models import (
    AbsorptionState,
    AggressionBias,
    ExhaustionState,
    FlowWindow,
    TrapRisk,
)
from ultimate_trader.orderflow_intelligence.orderflow_scenarios import (
    OrderFlowScenarioEngine,
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


class TestOrderFlowScenarioEngine:
    def test_dominant_scenario_with_evidence(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10, large_count=5)
        r = e.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.SHORT_TRAP_RISK)
        assert r.dominant_scenario == "genuine_buyer_accumulation"
        assert r.dominant_scenario in [s.name for s in r.scenarios]

    def test_no_edge_when_balanced(self):
        e = OrderFlowScenarioEngine()
        w = make_window(trade_count=2)
        r = e.analyze(w, AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LOW_TRAP_RISK)
        assert r.dominant_scenario == "no_edge_balanced_flow"
        assert r.no_edge_probability >= 50.0

    def test_passive_seller_absorption(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10)
        r = e.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.BUYING_ABSORBED, ExhaustionState.NO_EXHAUSTION, TrapRisk.LONG_TRAP_RISK)
        assert r.dominant_scenario == "passive_seller_absorption"

    def test_passive_buyer_absorption(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=20.0, sell_vol=80.0, trade_count=10)
        r = e.analyze(w, AggressionBias.SELLER_AGGRESSION, AbsorptionState.SELLING_ABSORBED, ExhaustionState.NO_EXHAUSTION, TrapRisk.SHORT_TRAP_RISK)
        assert r.dominant_scenario == "passive_buyer_absorption"

    def test_genuine_seller_distribution(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=20.0, sell_vol=80.0, trade_count=10, large_count=5)
        r = e.analyze(w, AggressionBias.SELLER_AGGRESSION, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LONG_TRAP_RISK)
        assert r.dominant_scenario == "genuine_seller_distribution"

    def test_exhaustion_reversal_scenario_present(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=10)
        r = e.analyze(w, AggressionBias.BALANCED, AbsorptionState.BUYING_ABSORBED, ExhaustionState.BUYER_EXHAUSTION, TrapRisk.LOW_TRAP_RISK)
        names = [s.name for s in r.scenarios]
        assert "exhaustion_reversal" in names

    def test_fake_breakout_scenario_present(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=50.0, sell_vol=50.0, trade_count=15, large_count=1)
        r = e.analyze(w, AggressionBias.BALANCED, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LONG_TRAP_RISK)
        names = [s.name for s in r.scenarios]
        assert "fake_breakout" in names

    def test_short_squeeze_scenario_present(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10)
        r = e.analyze(w, AggressionBias.SELLER_AGGRESSION, AbsorptionState.SELLING_ABSORBED, ExhaustionState.NO_EXHAUSTION, TrapRisk.SHORT_TRAP_RISK)
        names = [s.name for s in r.scenarios]
        assert "short_squeeze" in names

    def test_long_squeeze_scenario_present(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=20.0, sell_vol=80.0, trade_count=10)
        r = e.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.BUYING_ABSORBED, ExhaustionState.NO_EXHAUSTION, TrapRisk.LONG_TRAP_RISK)
        names = [s.name for s in r.scenarios]
        assert "long_squeeze" in names

    def test_scenarios_sorted_by_probability(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=10, large_count=5)
        r = e.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LOW_TRAP_RISK)
        for i in range(len(r.scenarios) - 1):
            assert r.scenarios[i].probability_estimate >= r.scenarios[i + 1].probability_estimate

    def test_top_five_scenarios_returned(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=70.0, sell_vol=30.0, trade_count=10, large_count=5)
        r = e.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LOW_TRAP_RISK)
        assert len(r.scenarios) <= 5

    def test_scenario_has_invalidation_condition(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10, large_count=5)
        r = e.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LOW_TRAP_RISK)
        for s in r.scenarios:
            assert s.invalidation_condition

    def test_summary_contains_dominant_and_alt(self):
        e = OrderFlowScenarioEngine()
        w = make_window(buy_vol=80.0, sell_vol=20.0, trade_count=10, large_count=5)
        r = e.analyze(w, AggressionBias.BUYER_AGGRESSION, AbsorptionState.NO_ABSORPTION, ExhaustionState.NO_EXHAUSTION, TrapRisk.LOW_TRAP_RISK)
        assert "dominant=" in r.scenario_summary
    