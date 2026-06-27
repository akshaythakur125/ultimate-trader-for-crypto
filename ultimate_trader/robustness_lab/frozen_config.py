from dataclasses import dataclass, field


@dataclass(frozen=True)
class FrozenConfig:
    rank_grade_a_plus_min: float = 85.0
    rank_grade_a_min: float = 70.0
    min_confluence_score: float = 50.0
    min_directional_confidence: float = 0.55
    max_conflict_score: float = 0.4
    max_reversal_risk_score: float = 50.0
    max_risk_score: float = 40.0
    min_rr: float = 3.0
    allowed_grades: tuple[str, ...] = ("A_PLUS", "A")
    target_trades_per_day: int = 3
    hard_max_per_day: int = 4
    same_symbol_cooldown_minutes: int = 120
    same_direction_cooldown_minutes: int = 180
    loss_threshold_increase: float = 0.10
    max_losses_per_day: int = 2
    rank_score_weights: tuple[tuple[str, float], ...] = (
        ("confluence", 0.25),
        ("directional_confidence", 0.15),
        ("conflict_inverse", 0.12),
        ("continuation", 0.10),
        ("reversal_risk_inverse", 0.08),
        ("target_realism", 0.08),
        ("stop_quality", 0.07),
        ("lsm_sweep_quality", 0.05),
        ("volatility_alignment", 0.05),
        ("orderflow_confirmation", 0.03),
        ("microstructure_confirmation", 0.02),
    )
    strategy_confidence_threshold: float = 60.0


def freeze_current_config() -> FrozenConfig:
    return FrozenConfig()


def config_summary(cfg: FrozenConfig) -> str:
    lines = []
    lines.append("Frozen Selectivity Config")
    lines.append("=" * 40)
    lines.append(f"  Grade A+ min score:     {cfg.rank_grade_a_plus_min}")
    lines.append(f"  Grade A min score:      {cfg.rank_grade_a_min}")
    lines.append(f"  Min confluence:         {cfg.min_confluence_score}")
    lines.append(f"  Min directional conf:   {cfg.min_directional_confidence}")
    lines.append(f"  Max conflict:           {cfg.max_conflict_score}")
    lines.append(f"  Max reversal risk:      {cfg.max_reversal_risk_score}")
    lines.append(f"  Max risk score:         {cfg.max_risk_score}")
    lines.append(f"  Min RR:                 {cfg.min_rr}")
    lines.append(f"  Allowed grades:         {', '.join(cfg.allowed_grades)}")
    lines.append(f"  Target trades/day:      {cfg.target_trades_per_day}")
    lines.append(f"  Hard max/day:           {cfg.hard_max_per_day}")
    lines.append(f"  Symbol cooldown (min):  {cfg.same_symbol_cooldown_minutes}")
    lines.append(f"  Direction cooldown (min): {cfg.same_direction_cooldown_minutes}")
    lines.append(f"  Loss threshold increase: {cfg.loss_threshold_increase}")
    lines.append(f"  Max losses/day:         {cfg.max_losses_per_day}")
    lines.append(f"  Strategy confidence:    {cfg.strategy_confidence_threshold}")
    return "\n".join(lines)
