import pytest
from ultimate_trader.directional_diagnostics.bias_component_attribution import (
    BiasComponentAttribution,
    ComponentAttributionResult,
)


def _names(items):
    return [c.split(" (")[0] for c in items]


class TestBiasComponentAttribution:
    def test_empty_components(self):
        attributor = BiasComponentAttribution()
        result = attributor.analyze([])
        assert len(result.components_helping_direction) == 0
        assert len(result.components_hurting_direction) == 0

    def test_all_components_help(self):
        attributor = BiasComponentAttribution()
        trades = []
        for i in range(10):
            trades.append({
                "directional_components": {"sweep_bias": 1.0, "fvg_bias": 1.0, "ob_bias": 1.0},
                "net_r": 2.0,
                "direction": "LONG",
                "is_winner": True,
            })
        result = attributor.analyze(trades)
        assert "sweep_bias" in result.components_helping_direction
        assert "fvg_bias" in result.components_helping_direction
        assert len(_names(result.components_hurting_direction)) == 0

    def test_all_components_hurt(self):
        attributor = BiasComponentAttribution()
        trades = []
        for i in range(10):
            trades.append({
                "directional_components": {"structure_bias": -1.0, "pd_bias": -1.0},
                "net_r": -2.0,
                "direction": "LONG",
                "is_winner": False,
            })
        result = attributor.analyze(trades)
        hurting_names = _names(result.components_hurting_direction)
        assert "structure_bias" in hurting_names
        assert "pd_bias" in hurting_names

    def test_mixed_components(self):
        attributor = BiasComponentAttribution()
        trades = []
        for i in range(10):
            comps = {"sweep_bias": 1.0, "structure_bias": -1.0}
            net_r = 2.0 if i < 7 else -1.0
            trades.append({
                "directional_components": comps,
                "net_r": net_r,
                "direction": "LONG",
                "is_winner": net_r > 0,
            })
        result = attributor.analyze(trades)
        total = len(_names(result.components_helping_direction)) + len(_names(result.components_hurting_direction))
        assert total > 0

    def test_unreliable_components(self):
        attributor = BiasComponentAttribution()
        trades = []
        for i in range(10):
            trades.append({
                "directional_components": {"unstable": 1.0 if i < 5 else -1.0, "stable": 1.0},
                "net_r": 1.0,
                "direction": "LONG",
                "is_winner": True,
            })
        result = attributor.analyze(trades)
        # "unstable" has 5 wins out of 10 = 50% WR, "stable" has 10/10 = 100% WR
        if result.unreliable_components:
            assert "unstable" not in result.unreliable_components  # 50% WR >= 50%

    def test_recommended_reweighting(self):
        attributor = BiasComponentAttribution()
        trades = []
        for i in range(10):
            trades.append({
                "directional_components": {"good": 1.0, "bad": -1.0},
                "net_r": 2.0 if i < 8 else -1.0,
                "direction": "LONG",
                "is_winner": i < 8,
            })
        result = attributor.analyze(trades)
        assert isinstance(result.recommended_reweighting, str)
        assert len(result.recommended_reweighting) > 0

    def test_no_data_returns_reliable_message(self):
        attributor = BiasComponentAttribution()
        result = attributor.analyze([{"directional_components": {}, "net_r": 0.0, "direction": "LONG", "is_winner": False}])
        assert result.recommended_reweighting == "All components appear directionally reliable"

    def test_components_to_disable(self):
        attributor = BiasComponentAttribution()
        trades = []
        for i in range(10):
            trades.append({
                "directional_components": {"bad_comp": -1.0 if i < 9 else 1.0, "good_comp": 1.0},
                "net_r": -1.0 if i < 9 else 2.0,
                "direction": "LONG",
                "is_winner": i >= 9,
            })
        result = attributor.analyze(trades)
        hurting_names = _names(result.components_hurting_direction)
        assert len(hurting_names) > 0
