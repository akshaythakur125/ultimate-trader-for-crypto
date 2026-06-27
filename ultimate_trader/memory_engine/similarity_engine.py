import math
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.memory_engine.case_library import CaseLibrary
from ultimate_trader.memory_engine.pattern_signature import PatternSignature


class PatternSimilarityResult(BaseModel):
    current_signature_id: str
    matched_case_id: str
    similarity_score: float
    matched_features: list[str] = Field(default_factory=list)
    mismatched_features: list[str] = Field(default_factory=list)
    similarity_summary: str = ""


class SimilarityEngine:
    CATEGORICAL_FIELDS = [
        "regime_label",
        "liquidity_state",
        "orderflow_state",
        "volatility_state",
        "trend_state",
        "funding_state",
        "open_interest_state",
        "manipulation_risk_state",
        "compression_state",
    ]

    def find_similar_cases(
        self,
        current_signature: PatternSignature,
        case_library: CaseLibrary,
        min_similarity: float = 70.0,
        limit: int = 10,
    ) -> list[PatternSimilarityResult]:
        results: list[PatternSimilarityResult] = []

        for case in case_library.list_cases():
            score = self._compute_similarity(
                current_signature, case.pattern_signature
            )
            if score >= min_similarity:
                matched, mismatched = self._compare_features(
                    current_signature, case.pattern_signature
                )
                results.append(
                    PatternSimilarityResult(
                        current_signature_id=current_signature.signature_id,
                        matched_case_id=case.case_id,
                        similarity_score=round(score, 1),
                        matched_features=matched,
                        mismatched_features=mismatched,
                        similarity_summary=(
                            f"Similarity {score:.0f}% — "
                            f"{len(matched)} matched, {len(mismatched)} mismatched"
                        ),
                    )
                )

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results[:limit]

    def compute_similarity(
        self,
        sig_a: PatternSignature,
        sig_b: PatternSignature,
    ) -> float:
        return self._compute_similarity(sig_a, sig_b)

    def _compute_similarity(
        self,
        sig_a: PatternSignature,
        sig_b: PatternSignature,
    ) -> float:
        cat_score = self._categorical_score(sig_a, sig_b)
        num_score = self._numeric_score(sig_a, sig_b)
        raw = cat_score * 0.6 + num_score * 0.4
        return raw * 100.0

    def _categorical_score(
        self,
        sig_a: PatternSignature,
        sig_b: PatternSignature,
    ) -> float:
        matches = 0
        total = 0
        for field in self.CATEGORICAL_FIELDS:
            val_a = getattr(sig_a, field, None)
            val_b = getattr(sig_b, field, None)
            if val_a is not None and val_b is not None:
                total += 1
                if val_a == val_b:
                    matches += 1
        if total == 0:
            return 0.0
        return matches / total

    def _numeric_score(
        self,
        sig_a: PatternSignature,
        sig_b: PatternSignature,
    ) -> float:
        keys_a = set(sig_a.feature_vector.keys())
        keys_b = set(sig_b.feature_vector.keys())
        if not keys_a and not keys_b:
            return 1.0
        all_keys = keys_a & keys_b
        if not all_keys:
            return 0.5

        distances: list[float] = []
        for key in all_keys:
            va = sig_a.feature_vector[key]
            vb = sig_b.feature_vector[key]
            diff = abs(va - vb)
            normalized = min(1.0, diff / 100.0)
            distances.append(1.0 - normalized)

        return sum(distances) / len(distances)

    def _compare_features(
        self,
        sig_a: PatternSignature,
        sig_b: PatternSignature,
    ) -> tuple[list[str], list[str]]:
        matched: list[str] = []
        mismatched: list[str] = []
        for field in self.CATEGORICAL_FIELDS:
            val_a = getattr(sig_a, field, None)
            val_b = getattr(sig_b, field, None)
            if val_a is not None and val_b is not None:
                if val_a == val_b:
                    matched.append(field)
                else:
                    mismatched.append(f"{field}: {val_a} vs {val_b}")
        return matched, mismatched
