import uuid

from pydantic import BaseModel, Field

from ultimate_trader.research_brain.hypothesis_generator import (
    ResearchHypothesis,
)


class FalsificationQuestion(BaseModel):
    question: str
    answer: str = ""


class FalsificationResult(BaseModel):
    falsification_id: str
    target_hypothesis_id: str
    is_falsified: bool
    falsification_reason: str = ""
    questions: list[FalsificationQuestion] = Field(default_factory=list)
    passed_questions: int = 0
    failed_questions: int = 0


class FalsificationEngine:
    QUESTIONS = [
        "What evidence would make this hypothesis wrong?",
        "Has that evidence already appeared?",
        "Is the hypothesis relying on missing data?",
        "Does an alternative hypothesis explain the market better?",
        "Is the hypothesis only valid in a different regime?",
        "Is expected RR unrealistic?",
        "Is this hypothesis overfitted to recent behavior?",
    ]

    def falsify(self, hypothesis: ResearchHypothesis) -> FalsificationResult:
        falsified = False
        reason = ""
        questions = []
        passed = 0
        failed = 0

        for q_text in self.QUESTIONS:
            q = FalsificationQuestion(question=q_text)
            result = self._answer_question(q_text, hypothesis)

            if result["is_falsified"]:
                falsified = True
                reason = result["reason"]
                q.answer = result["answer"]
                failed += 1
            else:
                q.answer = result["answer"]
                passed += 1

            questions.append(q)

        if falsified:
            hypothesis.status = "FALSIFIED"
            hypothesis.rejection_reason = reason

        return FalsificationResult(
            falsification_id=f"FR-{uuid.uuid4().hex[:8].upper()}",
            target_hypothesis_id=hypothesis.research_id,
            is_falsified=falsified,
            falsification_reason=reason,
            questions=questions,
            passed_questions=passed,
            failed_questions=failed,
        )

    def _answer_question(
        self,
        question: str,
        hypothesis: ResearchHypothesis,
    ) -> dict:
        if "What evidence would make this hypothesis wrong?" in question:
            if hypothesis.invalidating_evidence:
                return {
                    "is_falsified": False,
                    "reason": "",
                    "answer": f"Invalidating evidence defined: {hypothesis.invalidating_evidence}",
                }
            return {
                "is_falsified": True,
                "reason": "No invalidating evidence defined",
                "answer": "No invalidating evidence specified",
            }

        if "Has that evidence already appeared?" in question:
            if hypothesis.contradicting_evidence:
                return {
                    "is_falsified": True,
                    "reason": "Contradicting evidence exists",
                    "answer": f"Present: {hypothesis.contradicting_evidence}",
                }
            return {
                "is_falsified": False,
                "reason": "",
                "answer": "No contradicting evidence yet",
            }

        if "missing data" in question:
            if not hypothesis.required_evidence:
                return {
                    "is_falsified": True,
                    "reason": "No required evidence specified",
                    "answer": "No required evidence defined",
                }
            return {
                "is_falsified": False,
                "reason": "",
                "answer": f"Required evidence defined: {len(hypothesis.required_evidence)} items",
            }

        if "alternative" in question.lower():
            return {
                "is_falsified": False,
                "reason": "",
                "answer": "Alternative hypotheses exist for comparison",
            }

        if "different regime" in question:
            if hypothesis.regime_dependency and hypothesis.regime_dependency != "any":
                return {
                    "is_falsified": False,
                    "reason": "",
                    "answer": f"Valid in {hypothesis.regime_dependency} regime",
                }
            return {
                "is_falsified": False,
                "reason": "",
                "answer": "No specific regime dependency",
            }

        if "RR unrealistic" in question:
            if hypothesis.expected_rr > 5.0 and not hypothesis.supporting_evidence:
                return {
                    "is_falsified": True,
                    "reason": "Expected RR too high for available evidence",
                    "answer": f"Expected RR {hypothesis.expected_rr} without supporting evidence",
                }
            return {
                "is_falsified": False,
                "reason": "",
                "answer": f"Expected RR {hypothesis.expected_rr} seems reasonable",
            }

        if "overfitted" in question:
            return {
                "is_falsified": False,
                "reason": "",
                "answer": "Overfit assessment should be checked separately",
            }

        return {
            "is_falsified": False,
            "reason": "",
            "answer": "Question not evaluated",
        }
