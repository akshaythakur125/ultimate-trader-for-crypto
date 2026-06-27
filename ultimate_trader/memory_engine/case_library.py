import json
import os
from typing import Optional

from ultimate_trader.memory_engine.market_case import MarketCase, OutcomeLabel


class CaseLibrary:
    def __init__(self, storage_path: Optional[str] = None):
        self._cases: dict[str, MarketCase] = {}
        self._storage_path = storage_path
        if storage_path and os.path.exists(storage_path):
            self._load()

    def add_case(self, case: MarketCase) -> None:
        self._cases[case.case_id] = case
        if self._storage_path:
            self._save()

    def get_case(self, case_id: str) -> Optional[MarketCase]:
        return self._cases.get(case_id)

    def list_cases(self) -> list[MarketCase]:
        return list(self._cases.values())

    def filter_by_symbol(self, symbol: str) -> list[MarketCase]:
        return [c for c in self._cases.values() if c.symbol == symbol]

    def filter_by_regime(self, regime_label: str) -> list[MarketCase]:
        return [
            c
            for c in self._cases.values()
            if c.pattern_signature.regime_label == regime_label
        ]

    def filter_by_outcome(self, outcome_label: OutcomeLabel) -> list[MarketCase]:
        return [c for c in self._cases.values() if c.outcome_label == outcome_label]

    def filter_by_timeframe(self, timeframe: str) -> list[MarketCase]:
        return [c for c in self._cases.values() if c.timeframe == timeframe]

    def get_success_cases(self) -> list[MarketCase]:
        return [
            c
            for c in self._cases.values()
            if c.outcome_label in (OutcomeLabel.WIN,)
        ]

    def get_failure_cases(self) -> list[MarketCase]:
        return [
            c
            for c in self._cases.values()
            if c.outcome_label in (OutcomeLabel.LOSS, OutcomeLabel.BAD_NO_TRADE)
        ]

    def count(self) -> int:
        return len(self._cases)

    def clear(self) -> None:
        self._cases.clear()
        if self._storage_path:
            self._save()

    def _save(self) -> None:
        data = [
            c.model_dump() if hasattr(c, "model_dump") else c.dict()
            for c in self._cases.values()
        ]
        with open(self._storage_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load(self) -> None:
        with open(self._storage_path) as f:
            data = json.load(f)
        for item in data:
            case = MarketCase(**item)
            self._cases[case.case_id] = case
