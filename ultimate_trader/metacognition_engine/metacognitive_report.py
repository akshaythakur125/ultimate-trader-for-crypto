import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.bias_detector import BiasDetection
from ultimate_trader.metacognition_engine.counterfactual_reasoning import (
    CounterfactualQuestion,
)
from ultimate_trader.metacognition_engine.decision_auditor import DecisionAudit
from ultimate_trader.metacognition_engine.overconfidence_guard import (
    OverconfidenceAdjustment,
)
from ultimate_trader.metacognition_engine.scenario_simulator import (
    ScenarioSimulationResult,
)
from ultimate_trader.metacognition_engine.self_critique import SelfCritique
from ultimate_trader.metacognition_engine.trade_readiness import (
    TradeReadinessAssessment,
)


class MetacognitiveReport(BaseModel):
    report_id: str
    target_decision_id: str
    self_critique: Optional[SelfCritique] = None
    bias_detection: Optional[BiasDetection] = None
    scenario_simulation: Optional[ScenarioSimulationResult] = None
    counterfactual_questions: list[CounterfactualQuestion] = Field(
        default_factory=list
    )
    decision_audit: Optional[DecisionAudit] = None
    overconfidence_adjustment: Optional[OverconfidenceAdjustment] = None
    trade_readiness: Optional[TradeReadinessAssessment] = None
    final_summary: str = ""
    final_action: str = ""


class MetacognitiveReportGenerator:
    def generate(self, chain: ReasoningChain) -> MetacognitiveReport:
        from ultimate_trader.metacognition_engine.bias_detector import BiasDetector
        from ultimate_trader.metacognition_engine.counterfactual_reasoning import (
            CounterfactualReasoner,
        )
        from ultimate_trader.metacognition_engine.decision_auditor import DecisionAuditor
        from ultimate_trader.metacognition_engine.overconfidence_guard import (
            OverconfidenceGuard,
        )
        from ultimate_trader.metacognition_engine.scenario_simulator import (
            ScenarioSimulator,
        )
        from ultimate_trader.metacognition_engine.self_critique import SelfCritiqueEngine
        from ultimate_trader.metacognition_engine.trade_readiness import (
            TradeReadinessChecker,
        )

        self_critique = SelfCritiqueEngine().critique(chain)
        bias_detection = BiasDetector().detect(chain)
        scenario_simulation = ScenarioSimulator().simulate(chain)
        counterfactual_questions = CounterfactualReasoner().reason(chain)
        decision_audit = DecisionAuditor().audit(chain)
        overconfidence = OverconfidenceGuard().evaluate(chain)
        trade_readiness = TradeReadinessChecker().check(chain)

        summary_parts: list[str] = []
        action = "WAIT"

        if self_critique.should_reject_trade:
            summary_parts.append("Self-critique recommends rejection")
            action = "REJECT_IDEA"

        if bias_detection.detected_biases:
            bias_names = [
                b.value
                for b in bias_detection.detected_biases
                if b.value != "NONE"
            ]
            if bias_names:
                summary_parts.append(f"Biases detected: {', '.join(bias_names)}")

        if overconfidence and overconfidence.reduction_amount > 0:
            summary_parts.append(
                f"Overconfidence guard reduced confidence by "
                f"{overconfidence.reduction_amount:.0f} points"
            )

        if not decision_audit.audit_passed:
            summary_parts.append("Decision audit failed")
            if action == "REJECT_IDEA":
                pass
            else:
                action = "HUMAN_REVIEW"

        if trade_readiness:
            action = trade_readiness.final_recommendation.value
            summary_parts.append(
                f"Readiness score: {trade_readiness.readiness_score:.0f}/100"
            )
            if trade_readiness.blocking_reasons:
                summary_parts.append(
                    f"Blocking: {trade_readiness.blocking_reasons[0]}"
                )

        if not summary_parts:
            summary_parts.append("Meta-cognition completed — no critical issues")

        return MetacognitiveReport(
            report_id=f"MCR-{uuid.uuid4().hex[:8].upper()}",
            target_decision_id=chain.chain_id,
            self_critique=self_critique,
            bias_detection=bias_detection,
            scenario_simulation=scenario_simulation,
            counterfactual_questions=counterfactual_questions.counterfactual_questions,
            decision_audit=decision_audit,
            overconfidence_adjustment=overconfidence,
            trade_readiness=trade_readiness,
            final_summary=" | ".join(summary_parts),
            final_action=action,
        )
