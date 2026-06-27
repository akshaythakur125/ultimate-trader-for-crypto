import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain


class CounterfactualQuestion(BaseModel):
    question_id: str
    target_decision_id: str
    question: str
    answer: str = ""
    impact_on_confidence: float = 0.0
    impact_on_risk: float = 0.0
    follow_up_required: bool = False


_COUNTERFACTUAL_TEMPLATES = [
    {
        "question": "What evidence would make this trade invalid?",
        "confidence_impact": -10.0,
        "risk_impact": 5.0,
    },
    {
        "question": "What if the breakout is a trap?",
        "confidence_impact": -15.0,
        "risk_impact": 10.0,
    },
    {
        "question": "What if liquidity is taken before the real move?",
        "confidence_impact": -10.0,
        "risk_impact": 8.0,
    },
    {
        "question": "What if volatility expands against the trade?",
        "confidence_impact": -10.0,
        "risk_impact": 12.0,
    },
    {
        "question": "What if this is a chop regime disguised as opportunity?",
        "confidence_impact": -15.0,
        "risk_impact": 10.0,
    },
    {
        "question": "What if the target is unrealistic?",
        "confidence_impact": -8.0,
        "risk_impact": 5.0,
    },
    {
        "question": "What if the stop is placed where obvious liquidity exists?",
        "confidence_impact": -10.0,
        "risk_impact": 10.0,
    },
]


class CounterfactualReasoningResult(BaseModel):
    counterfactual_questions: list[CounterfactualQuestion]
    key_insight: str = ""


class CounterfactualReasoner:
    def reason(self, chain: ReasoningChain) -> CounterfactualReasoningResult:
        questions = self.generate_questions(chain)
        key_insight_parts: list[str] = []
        high_impact = [q for q in questions if abs(q.impact_on_confidence) >= 15]
        if high_impact:
            key_insight_parts.append(
                f"{len(high_impact)} high-impact counterfactual(s) identified"
            )
        total_impact = self.get_total_confidence_impact(questions)
        key_insight_parts.append(f"Total confidence impact: {total_impact:.0f}")
        return CounterfactualReasoningResult(
            counterfactual_questions=questions,
            key_insight=". ".join(key_insight_parts),
        )

    def generate_questions(
        self, chain: ReasoningChain
    ) -> list[CounterfactualQuestion]:
        questions: list[CounterfactualQuestion] = []
        for tmpl in _COUNTERFACTUAL_TEMPLATES:
            answer = self._answer_question(tmpl["question"], chain)
            questions.append(
                CounterfactualQuestion(
                    question_id=f"CFQ-{uuid.uuid4().hex[:8].upper()}",
                    target_decision_id=chain.chain_id,
                    question=tmpl["question"],
                    answer=answer,
                    impact_on_confidence=tmpl["confidence_impact"],
                    impact_on_risk=tmpl["risk_impact"],
                    follow_up_required=bool(chain.missing_evidence
                    and "evidence" in tmpl["question"].lower()),
                )
            )
        return questions

    def _answer_question(self, question: str, chain: ReasoningChain) -> str:
        q = question.lower()

        if "evidence" in q and "invalidate" in q:
            if chain.missing_evidence:
                return (
                    f"The trade would be invalidated if: "
                    f"{' or '.join(chain.missing_evidence[:3])} "
                    f"proves the hypothesis wrong."
                )
            return "Missing evidence could invalidate — currently unknown."

        if "trap" in q:
            if chain.contradictions:
                return (
                    f"Trap risk is present — {len(chain.contradictions)} "
                    f"contradiction(s) detected."
                )
            return "No trap signals currently detected, but not ruled out."

        if "liquidity" in q:
            return "Liquidity sweeps are common — the move may be a grab."

        if "volatility" in q:
            return (
                f"Volatility expanding against the trade "
                f"would increase risk significantly "
                f"(current uncertainty: {chain.uncertainty_score:.0f}/100)."
            )

        if "chop" in q:
            if chain.uncertainty_score > 50:
                return (
                    f"Chop is possible — uncertainty is "
                    f"{chain.uncertainty_score:.0f}/100."
                )
            return "Regime appears directional, but chop remains a risk."

        if "target" in q:
            return (
                f"Target realism depends on volatility and evidence strength. "
                f"Current confidence: {chain.confidence_after:.0f}/100."
            )

        if "stop" in q:
            return (
                "Stops placed at obvious levels are likely targets "
                "for liquidity sweeps. Consider placing stops beyond "
                "obvious clusters."
            )

        return "Insufficient data to answer this counterfactual."

    def get_total_confidence_impact(
        self, questions: list[CounterfactualQuestion]
    ) -> float:
        return sum(q.impact_on_confidence for q in questions)

    def get_total_risk_impact(
        self, questions: list[CounterfactualQuestion]
    ) -> float:
        return sum(q.impact_on_risk for q in questions)
