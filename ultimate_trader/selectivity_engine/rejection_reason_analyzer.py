from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RejectionStats:
    low_rank: int = 0
    confluence: int = 0
    directional_confidence: int = 0
    conflict: int = 0
    reversal_risk: int = 0
    risk: int = 0
    rr: int = 0
    overtrading: int = 0
    cooldown: int = 0
    uncertainty: int = 0


class RejectionReasonAnalyzer:
    def __init__(self):
        self._stats = RejectionStats()
        self._reasons: list[tuple[str, str, str]] = []  # (candidate_id, category, reason)

    @property
    def stats(self) -> RejectionStats:
        return self._stats

    @property
    def reasons(self) -> list[tuple[str, str, str]]:
        return list(self._reasons)

    def record(self, candidate_id: str, category: str, reason: str):
        self._reasons.append((candidate_id, category, reason))
        if category == "low_rank":
            self._stats.low_rank += 1
        elif category == "confluence":
            self._stats.confluence += 1
        elif category == "directional_confidence":
            self._stats.directional_confidence += 1
        elif category == "conflict":
            self._stats.conflict += 1
        elif category == "reversal_risk":
            self._stats.reversal_risk += 1
        elif category == "risk":
            self._stats.risk += 1
        elif category == "rr":
            self._stats.rr += 1
        elif category == "overtrading":
            self._stats.overtrading += 1
        elif category == "cooldown":
            self._stats.cooldown += 1
        elif category == "uncertainty":
            self._stats.uncertainty += 1

    def reset(self):
        self._stats = RejectionStats()
        self._reasons.clear()
