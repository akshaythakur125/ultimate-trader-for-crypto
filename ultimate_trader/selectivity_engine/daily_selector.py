from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ultimate_trader.selectivity_engine.candidate_ranker import RankedCandidate
from ultimate_trader.selectivity_engine.quality_gate import QualityGate, QualityGateConfig, QualityGateResult


@dataclass
class DailySelectorConfig:
    target_trades_per_day: int = 3
    hard_max_per_day: int = 4
    min_a_plus_to_reach_target: int = 2
    same_symbol_cooldown_minutes: int = 120
    same_direction_cooldown_minutes: int = 180
    loss_threshold_increase: float = 0.10
    max_losses_per_day: int = 2


@dataclass
class DailySelectionResult:
    trade_id: str = ""
    direction: str = ""
    timestamp: Any = None
    allowed: bool = False
    rejection_reason: str = ""
    rejection_category: str = ""
    daily_count: int = 0
    daily_wins: int = 0
    daily_losses: int = 0


class DailySelector:
    def __init__(
        self,
        quality_gate: QualityGate,
        config: Optional[DailySelectorConfig] = None,
    ):
        self._quality_gate = quality_gate
        self._config = config or DailySelectorConfig()
        self._daily_counts: dict[str, int] = defaultdict(int)
        self._daily_losses: dict[str, int] = defaultdict(int)
        self._daily_wins: dict[str, int] = defaultdict(int)
        self._last_trade_by_symbol: dict[str, datetime] = {}
        self._last_trade_by_direction: dict[str, datetime] = {}
        self._selected_ids: set[str] = set()
        self._daily_candidates: dict[str, list[RankedCandidate]] = defaultdict(list)

    @property
    def config(self) -> DailySelectorConfig:
        return self._config

    def register_candidate(self, rc: RankedCandidate):
        if rc.timestamp is None:
            return
        day_key = rc.timestamp.strftime("%Y-%m-%d") if hasattr(rc.timestamp, "strftime") else "unknown"
        self._daily_candidates[day_key].append(rc)

    def select_for_day(self, day_key: str) -> list[tuple[RankedCandidate, DailySelectionResult]]:
        candidates = self._daily_candidates.get(day_key, [])
        if not candidates:
            return []

        day_losses = self._daily_losses.get(day_key, 0)
        if day_losses >= self._config.max_losses_per_day:
            return []

        results: list[tuple[RankedCandidate, DailySelectionResult]] = []
        day_count = self._daily_counts.get(day_key, 0)

        candidates.sort(key=lambda c: c.rank_score, reverse=True)

        for rc in candidates:
            if day_count >= self._config.hard_max_per_day:
                result = DailySelectionResult(
                    trade_id=rc.candidate_id, direction=rc.direction,
                    timestamp=rc.timestamp, allowed=False,
                    rejection_reason="Daily hard max reached",
                    rejection_category="overtrading",
                    daily_count=day_count,
                    daily_losses=day_losses,
                )
                results.append((rc, result))
                continue

            if day_losses >= self._config.max_losses_per_day:
                result = DailySelectionResult(
                    trade_id=rc.candidate_id, direction=rc.direction,
                    timestamp=rc.timestamp, allowed=False,
                    rejection_reason=f"Max losses per day ({self._config.max_losses_per_day}) reached",
                    rejection_category="overtrading",
                    daily_count=day_count,
                    daily_losses=day_losses,
                )
                results.append((rc, result))
                continue

            qg_config = QualityGateConfig(
                min_confluence_score=self._quality_gate.config.min_confluence_score + (self._config.loss_threshold_increase * 100 * day_losses),
                min_directional_confidence=min(self._quality_gate.config.min_directional_confidence + self._config.loss_threshold_increase * day_losses, 1.0),
                max_conflict_score=self._quality_gate.config.max_conflict_score,
                max_reversal_risk_score=self._quality_gate.config.max_reversal_risk_score,
                max_risk_score=min(self._quality_gate.config.max_risk_score + 10 * day_losses, 100),
                min_rr=self._quality_gate.config.min_rr,
                allowed_grades=self._quality_gate.config.allowed_grades,
            )
            tight_gate = QualityGate(qg_config)
            qr = tight_gate.evaluate(rc)

            if not qr.passed:
                result = DailySelectionResult(
                    trade_id=rc.candidate_id, direction=rc.direction,
                    timestamp=rc.timestamp, allowed=False,
                    rejection_reason=qr.rejection_reason,
                    rejection_category=qr.rejection_category,
                    daily_count=day_count,
                    daily_losses=day_losses,
                )
                results.append((rc, result))
                continue

            direction = rc.direction
            symbol = rc.symbol
            ts = rc.timestamp

            if direction in self._last_trade_by_direction:
                elapsed = (ts - self._last_trade_by_direction[direction]).total_seconds() / 60
                if elapsed < self._config.same_direction_cooldown_minutes:
                    result = DailySelectionResult(
                        trade_id=rc.candidate_id, direction=direction,
                        timestamp=ts, allowed=False,
                        rejection_reason=f"Same-direction cooldown: {elapsed:.0f}m < {self._config.same_direction_cooldown_minutes}m",
                        rejection_category="cooldown",
                        daily_count=day_count,
                        daily_losses=day_losses,
                    )
                    results.append((rc, result))
                    continue

            if symbol in self._last_trade_by_symbol:
                elapsed = (ts - self._last_trade_by_symbol[symbol]).total_seconds() / 60
                if elapsed < self._config.same_symbol_cooldown_minutes:
                    result = DailySelectionResult(
                        trade_id=rc.candidate_id, direction=direction,
                        timestamp=ts, allowed=False,
                        rejection_reason=f"Same-symbol cooldown: {elapsed:.0f}m < {self._config.same_symbol_cooldown_minutes}m",
                        rejection_category="cooldown",
                        daily_count=day_count,
                        daily_losses=day_losses,
                    )
                    results.append((rc, result))
                    continue

            self._daily_counts[day_key] += 1
            self._last_trade_by_direction[direction] = ts
            self._last_trade_by_symbol[symbol] = ts
            self._selected_ids.add(rc.candidate_id)
            day_count += 1

            result = DailySelectionResult(
                trade_id=rc.candidate_id, direction=direction,
                timestamp=ts, allowed=True,
                daily_count=day_count,
                daily_losses=day_losses,
            )
            results.append((rc, result))

        return results

    def record_outcome(self, candidate_id: str, was_winner: bool, day_key: str):
        if was_winner:
            self._daily_wins[day_key] += 1
        else:
            self._daily_losses[day_key] += 1

    def reset(self):
        self._daily_counts.clear()
        self._daily_losses.clear()
        self._daily_wins.clear()
        self._last_trade_by_symbol.clear()
        self._last_trade_by_direction.clear()
        self._selected_ids.clear()
        self._daily_candidates.clear()
