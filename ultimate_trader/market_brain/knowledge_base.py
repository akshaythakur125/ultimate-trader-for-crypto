from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.market_brain.market_principles import (
    CategoryEnum,
    MarketPrinciple,
    get_all_principles,
    AUCTION_PRINCIPLES,
    LIQUIDITY_PRINCIPLES,
    ORDERFLOW_PRINCIPLES,
    VOLATILITY_PRINCIPLES,
    REGIME_PRINCIPLES,
    MANIPULATION_PRINCIPLES,
    BEHAVIORAL_PRINCIPLES,
    PROBABILITY_PRINCIPLES,
    RISK_PRINCIPLES,
)

_NO_TRADE_KEYWORDS = [
    "no-trade",
    "no_trade",
    "skip",
    "uncertain",
    "choppy",
    "unfavorable",
    "conflicting",
    "contradict",
]
_LIQUIDITY_MANIPULATION_KEYWORDS = [
    "sweep",
    "stop",
    "trap",
    "fakeout",
    "manipulation",
    "liquidity",
    "reclaim",
]
_VOLATILITY_EXPANSION_KEYWORDS = [
    "compression",
    "expansion",
    "volatility",
    "squeeze",
    "range",
    "atr",
]


class KnowledgeBaseQuery(BaseModel):
    condition: str
    keywords: list[str] = Field(default_factory=list)
    categories: list[CategoryEnum] = Field(default_factory=list)


class MarketReasoningContext(BaseModel):
    symbol: str
    timeframe: str
    observed_conditions: list[str] = Field(default_factory=list)
    relevant_principles: list[MarketPrinciple] = Field(default_factory=list)
    supporting_principles: list[MarketPrinciple] = Field(default_factory=list)
    contradicting_principles: list[MarketPrinciple] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    preliminary_interpretation: str = ""


class MarketKnowledgeBase:
    def __init__(self) -> None:
        self._principles: dict[str, MarketPrinciple] = {}
        self._by_category: dict[CategoryEnum, list[MarketPrinciple]] = {
            cat: [] for cat in CategoryEnum
        }
        self._loaded = False
        self._load()

    def _load(self) -> None:
        all_principles = get_all_principles()
        for p in all_principles:
            self._principles[p.principle_id] = p
            self._by_category[p.category].append(p)
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def principle_count(self) -> int:
        return len(self._principles)

    def get_all(self) -> list[MarketPrinciple]:
        return list(self._principles.values())

    def get_by_id(self, principle_id: str) -> Optional[MarketPrinciple]:
        return self._principles.get(principle_id)

    def get_by_category(self, category: CategoryEnum) -> list[MarketPrinciple]:
        return list(self._by_category.get(category, []))

    def query(self, query: KnowledgeBaseQuery) -> list[MarketPrinciple]:
        results: list[MarketPrinciple] = []
        seen: set[str] = set()
        terms = [query.condition.lower()] + [k.lower() for k in query.keywords]

        for p in self._principles.values():
            if query.categories and p.category not in query.categories:
                continue
            text = (
                p.name.lower()
                + " "
                + p.description.lower()
                + " "
                + p.why_it_matters.lower()
            )
            if any(t in text for t in terms) and p.principle_id not in seen:
                results.append(p)
                seen.add(p.principle_id)

        return sorted(results, key=lambda x: x.principle_id)

    def find_principles_by_condition(self, condition: str) -> list[MarketPrinciple]:
        return self.query(KnowledgeBaseQuery(condition=condition))

    def get_principles_by_category(self, category: CategoryEnum) -> list[MarketPrinciple]:
        return self.get_by_category(category)

    def get_principles_for_keyword(self, keyword: str) -> list[MarketPrinciple]:
        return self.query(KnowledgeBaseQuery(condition=keyword))

    def get_no_trade_principles(self) -> list[MarketPrinciple]:
        return self.query(
            KnowledgeBaseQuery(condition="", keywords=_NO_TRADE_KEYWORDS)
        )

    def get_liquidity_manipulation_principles(self) -> list[MarketPrinciple]:
        return self.query(
            KnowledgeBaseQuery(
                condition="", keywords=_LIQUIDITY_MANIPULATION_KEYWORDS
            )
        )

    def get_volatility_expansion_principles(self) -> list[MarketPrinciple]:
        return self.query(
            KnowledgeBaseQuery(
                condition="", keywords=_VOLATILITY_EXPANSION_KEYWORDS
            )
        )

    def get_principles_that_warn_against_trading(self) -> list[MarketPrinciple]:
        return self.get_no_trade_principles()

    def build_reasoning_context(
        self,
        symbol: str,
        timeframe: str,
        observed_conditions: list[str],
    ) -> MarketReasoningContext:
        context = MarketReasoningContext(
            symbol=symbol,
            timeframe=timeframe,
            observed_conditions=observed_conditions,
        )

        seen_ids: set[str] = set()
        for condition in observed_conditions:
            found = self.find_principles_by_condition(condition)
            for p in found:
                if p.principle_id not in seen_ids:
                    context.relevant_principles.append(p)
                    seen_ids.add(p.principle_id)

        no_trade_keywords = set(_NO_TRADE_KEYWORDS)
        for p in context.relevant_principles:
            p_text = (
                p.name.lower() + " " + p.description.lower() + " "
                + p.why_it_matters.lower()
            )
            is_against = any(kw in p_text for kw in no_trade_keywords)

            if is_against:
                context.contradicting_principles.append(p)
            else:
                context.supporting_principles.append(p)

        if not context.relevant_principles:
            context.uncertainty_notes.append(
                "No relevant principles found for observed conditions."
            )

        context.preliminary_interpretation = self._generate_interpretation(context)
        return context

    def _generate_interpretation(self, context: MarketReasoningContext) -> str:
        parts = []
        if context.supporting_principles:
            parts.append(
                f"Supported by {len(context.supporting_principles)} principles"
            )
        if context.contradicting_principles:
            parts.append(
                f"Contradicted by {len(context.contradicting_principles)} principles"
            )
        if context.uncertainty_notes:
            parts.append(f"Uncertainties: {len(context.uncertainty_notes)}")

        if not parts:
            return "No clear interpretation available."

        return ". ".join(parts) + "."

    def health_check(self) -> dict[str, bool]:
        checks = {
            "knowledge_base_loaded": self.is_loaded,
            "has_auction_principles": len(self.get_by_category(CategoryEnum.AUCTION_MARKET)) > 0,
            "has_liquidity_principles": len(self.get_by_category(CategoryEnum.LIQUIDITY)) > 0,
            "has_orderflow_principles": len(self.get_by_category(CategoryEnum.ORDER_FLOW)) > 0,
            "has_volatility_principles": len(self.get_by_category(CategoryEnum.VOLATILITY)) > 0,
            "has_regime_principles": len(self.get_by_category(CategoryEnum.REGIME)) > 0,
            "has_manipulation_principles": len(self.get_by_category(CategoryEnum.MANIPULATION)) > 0,
            "has_behavioral_principles": len(self.get_by_category(CategoryEnum.BEHAVIORAL)) > 0,
            "has_probability_principles": len(self.get_by_category(CategoryEnum.PROBABILITY)) > 0,
            "has_risk_principles": len(self.get_by_category(CategoryEnum.RISK)) > 0,
            "no_trade_principles_available": len(self.get_no_trade_principles()) > 0,
            "liquidity_manipulation_principles_available": len(
                self.get_liquidity_manipulation_principles()
            )
            > 0,
            "volatility_expansion_principles_available": len(
                self.get_volatility_expansion_principles()
            )
            > 0,
        }
        return checks
