# Ultimate Trader

**Autonomous Intraday Crypto Futures Trading Intelligence System**

Ultimate Trader is not a scanner, not a single trading strategy, and not a normal bot. It is a full intelligent trading system designed to behave like a professional trading desk — observing markets, generating hypotheses, analyzing regime and liquidity, interpreting order flow, making probabilistic decisions, managing risk, backtesting, learning, and controlling execution.

## Prompt Progress

### Prompt 1 — Intelligence Operating Foundation
- Configuration system, safety, health checks
- Pydantic schema contracts for all data models
- Abstract interfaces for all 12 intelligence engines
- Reasoning and confidence assessment models
- SQLite database with 11 ORM tables
- Strategy and exchange agnostic — no trading logic

### Prompt 2 — Market Knowledge Framework
- 53 structured market principles across 9 categories
- Auction Market, Liquidity, Order Flow, Volatility, Regime,
  Manipulation, Behavioral, Probability, and Risk theory modules
- `MarketKnowledgeBase` — queryable principle repository
- `MarketReasoningContext` — condition-to-principle mapping
- `KnowledgeBaseQuery` — future modules can ask "what applies?"
- Reasoning helpers for no-trade, liquidity-manipulation, and
  volatility-expansion conditions

### Prompt 3 — Cognitive Reasoning Engine
- `Observation` model with 11 observation types
- `MarketInterpretation` engine mapping observations to meanings
- `AlternativeHypothesis` generation from observations
- `EvidenceEvaluator` — scores, separates, detects missing evidence
- `ContradictionDetector` — 6 generic contradiction rules
- `UncertaintyEngine` — 8 uncertainty factors assessed
- `ConfidenceUpdater` — baseline scoring with modifiers
- `ReasoningChain` — full chain from observation to conclusion
- `CognitiveDecisionContext` — action recommendation engine
- `CognitiveReportGenerator` — explainable decision reports
- Integrates with `MarketKnowledgeBase` from Prompt 2

### Prompt 4 — Meta-Cognition Engine
- `SelfCritiqueEngine` — argues for/against decisions, identifies ignored risks
- `BiasDetector` — 7 bias types (confirmation, overconfidence, forced trade, recency, revenge, crowd, anchoring)
- `ScenarioSimulator` — 5 alternative scenarios with probability normalization
- `CounterfactualReasoner` — 7 counterfactual questions about the decision
- `DecisionAuditor` — 7-score audit with pass/fail and required corrections
- `OverconfidenceGuard` — purely reductive confidence adjustment
- `TradeReadinessChecker` — blocks live trading, scores readiness (0–100)
- `MetacognitiveReportGenerator` — aggregates all audits into final recommendation

### Prompt 5 — Market Memory & Pattern Intelligence Engine
- `PatternSignature` — compact representation of a market condition (12 categorical fields + numeric feature vector)
- `MarketCase` — structured historical market situation with outcome tracking
- `CaseLibrary` — case storage and retrieval (add/get/filter by symbol/regime/outcome/timeframe)
- `SimilarityEngine` — categorical and numeric similarity scoring (0–100%), finds top similar cases
- `OutcomeMemory` — win rate, average R:R, expectancy, failure rate calculations; outcome summaries by regime/symbol/timeframe
- `FailureMemory` — identifies common failure reasons, high-failure regimes, generates failure warnings
- `SuccessMemory` — identifies common success reasons, high-success regimes, generates success support
- `RegimeMemory` — tracks best and dangerous regimes, regime warnings
- `ConfidenceCalibrator` — adjusts confidence/risk using historical analogs; marks insufficient memory
- `MemoryReport` — aggregates similar cases, outcomes, success/failure patterns, regime warnings, calibration

### Prompt 6 — Bayesian Belief & Expected Value Engine
- `MarketBelief` — represents one possible market scenario (6 competing beliefs with prior/posterior probabilities)
- `BeliefState` — manages all competing beliefs, normalizes probabilities, calculates entropy/conflict/no-trade probability
- `EvidenceLikelihood` — models how evidence supports or contradicts a specific belief
- `BayesianUpdater` — full Bayesian update: posterior = prior * likelihood ratio, with reliability-weighted evidence
- `ScenarioProbabilityEngine` — initializes 6 default beliefs (Breakout, Liquidity Sweep, False Breakout, Reversal, Range, Chop/No Trade), updates from evidence, rejects below threshold
- `ExpectedValueCalculator` — EV = p(win)×avg_win_R − p(loss)×avg_loss_R; computes breakeven win rate and margin of safety
- `RiskAdjustedUtilityEngine` — penalizes EV for uncertainty, drawdown, contradictions, and weak memory support; grades EXCELLENT→NO_TRADE
- `ProbabilityCalibrator` — pulls probabilities toward historical win rates, adjusts for sample size, memory support/warnings
- `DecisionThresholds` — 5-gate check: positive EV, utility grade, no-trade dominance, uncertainty, breakeven requirement
- `BeliefReport` — aggregates belief state, EV, utility, calibration, and thresholds into final recommendation

**Still no strategy. No BingX connection. No buy/sell rules.**

The purpose is to build a **research-grade system** that can prove statistical edge before risking capital.

## What's Included

- Configuration system with Pydantic settings
- Safety system blocking live trading by default
- Health check system
- Complete Pydantic schema contracts for all data models
- Abstract interfaces for all intelligence engines
- Reasoning and confidence assessment models
- SQLite database with full schema
- Hypothesis registry foundation
- Comprehensive test suite

## Installation

```bash
pip install -r requirements.txt
```

## Environment Setup

```bash
cp .env.example .env
# Edit .env with your configuration
```

## Run

```bash
python -m ultimate_trader.main
```

## Test

```bash
pytest
```

## Project Structure

```
ultimate_trader/
  main.py                    # Entry point
  config/                    # Settings and configuration
  core/                      # Logger, errors, safety, health, constants
  schemas/                   # All Pydantic data models
  intelligence/              # Core intelligence (reasoning, confidence)
  market_brain/              # Market knowledge framework (Prompt 2)
    market_principles.py     # 45+ principles across 9 categories
    auction_theory.py        # Auction market theory
    liquidity_theory.py      # Liquidity theory
    orderflow_theory.py      # Order flow theory (via volatility_theory)
    volatility_theory.py     # Volatility theory
    regime_theory.py         # Regime theory
    manipulation_theory.py   # Manipulation theory
    behavioral_theory.py     # Behavioral theory
    probability_theory.py    # Probability theory
    microstructure.py        # Microstructure concepts
    knowledge_base.py        # Queryable knowledge base + reasoning context
  cognitive_engine/          # Cognitive reasoning engine (Prompt 3)
    observation.py           # Observation model and types
    interpretation.py        # Market interpretation engine
    hypothesis_reasoning.py  # Alternative hypothesis generation
    evidence_evaluator.py    # Evidence scoring and separation
    contradiction_detector.py# Generic contradiction rules
    uncertainty_engine.py    # Uncertainty assessment
    confidence_updater.py    # Confidence scoring system
    reasoning_chain.py       # Full reasoning orchestrator
    decision_context.py      # Decision context and next action
    cognitive_report.py      # Explainable decision reports
  metacognition_engine/      # Meta-cognition engine (Prompt 4)
    self_critique.py         # Self-critique engine
    bias_detector.py         # Bias detection (7 bias types)
    scenario_simulator.py    # Scenario simulation
    counterfactual_reasoning.py # Counterfactual reasoning
    decision_auditor.py      # Decision audit
    overconfidence_guard.py  # Overconfidence guard
    trade_readiness.py       # Trade readiness assessment
    metacognitive_report.py  # Meta-cognitive report
  memory_engine/             # Market memory & pattern intelligence (Prompt 5)
    pattern_signature.py     # Pattern signature model
    market_case.py           # Market case model
    case_library.py          # Case storage and retrieval
    similarity_engine.py     # Similarity scoring engine
    outcome_memory.py        # Outcome analysis
    failure_memory.py        # Failure pattern tracking
    success_memory.py        # Success pattern tracking
    regime_memory.py         # Regime performance tracking
    confidence_calibrator.py # Confidence calibration from history
    memory_report.py         # Memory retrieval report
  belief_engine/             # Bayesian belief & expected value (Prompt 6)
    market_belief.py         # Market belief model
    belief_state.py          # Competing belief state manager
    evidence_likelihood.py   # Evidence likelihood model
    bayesian_updater.py      # Bayesian update logic
    scenario_probability.py  # Scenario probability engine
    expected_value.py        # Expected value calculator
    risk_adjusted_utility.py # Risk-adjusted utility engine
    probability_calibrator.py# Probability calibration from history
    decision_thresholds.py   # Decision threshold evaluation
    belief_report.py         # Belief engine report
  research_engine/           # Hypothesis registry
  data_engine/               # Data provider interface
  perception_engine/         # Market perception interface
  regime_engine/             # Market regime classification interface
  liquidity_engine/          # Liquidity analysis interface
  orderflow_engine/          # Order flow analysis interface
  probability_engine/        # Probabilistic decision interface
  validation_engine/         # Trade validation interface
  backtest_engine/           # Backtesting interface
  learning_engine/           # Learning and adaptation interface
  risk_engine/               # Risk management interface
  execution_engine/          # Trade execution interface
  alerts/                    # Alerting interface
  storage/                   # Database initialization and models
tests/                       # Test suite
```
