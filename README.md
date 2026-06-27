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

### Prompt 7 — Multi-Hypothesis Research Engine
- `HypothesisGenerator` — 12 hypothesis families (Breakout Continuation, Liquidity Sweep Reversal/Continuation, False Breakout, Short/Long Squeeze, Range Continuation, Mean Reversion, Trend Exhaustion, Volatility Expansion, Chop/No Trade, No Edge)
- `ResearchHypothesis` — structured hypothesis with direction bias, evidence requirements, failure modes, regime/liquidity/orderflow dependencies
- `HypothesisCompetitionEngine` — scores and selects winner among competing hypotheses
- `FalsificationEngine` — 7 Popperian falsification questions to test hypothesis integrity
- `ExplanatoryPowerScorer` — rates how well a hypothesis explains current market conditions
- `PredictivePowerScorer` — rates falsifiability and specificity of predictions
- `RobustnessChecker` — 6 structural checks (evidence, falsifiability, regime specificity, failure awareness, RR reasonableness)
- `OverfitGuard` — flags overfit risk with flags and recommendations
- `HypothesisRanker` — composites all scores into ordered rank
- Pipeline: Generator → Falsification → Competition → Scorers → Rank → Report

### Prompt 8 — Event Bus + Scientific Validation Engine
**Event Bus Foundation:**
- `BaseEvent` — 19 event types covering the full intelligence pipeline
- `EventBus` — sync pub/sub with wildcard support and fault isolation
- `EventStore` — JSON-persisted event storage with type and correlation-id queries
- `publish_system_event()` — helper for system-wide event publishing

**Scientific Validation Engine:**
- `TradingExperiment` — structured experiment definition with status tracking
- `DatasetSplitter` — non-overlapping train/validation/OOS splits with walk-forward windows
- `BacktestProtocol` — minimum trades, fee/slippage/funding inclusion, rejection rules
- `TradeResult` & `PerformanceMetrics` — full trade/performance model (win rate, expectancy, profit factor, drawdown, Sharpe-like ratio, consecutive losses, false signal rate)
- `TransactionCostModel` — configurable taker/maker fees, slippage, funding with net R calculation
- `WalkForwardValidator` — multi-window performance consistency with decay detection
- `OutOfSampleValidator` — validation vs OOS degradation check
- `MonteCarloSimulator` — 1000+ simulations, worst-case drawdown, probability of ruin, confidence intervals
- `SensitivityAnalysis` — higher fees, higher slippage, lower win rate, lower RR scenarios
- `ABTestingEngine` — compares two hypotheses, prefers simpler model when performance is similar
- `ValidationGate` — 9-gate check: minimum trades, positive expectancy, profit factor >1.2, drawdown limits, walk-forward, OOS, Monte Carlo, sensitivity, overfit; grades EXCELLENT/GOOD/MARGINAL/FAILED
- `ValidationReport` — aggregates all results with recommended next action
- Validation uses the event bus (publishes VALIDATION_STARTED, COMPLETED, FAILED, PASSED)
- `eligible_for_live_trading` always disabled

### Prompt 9 — Signal Intelligence & Trade Planning Engine
- `SignalContext` — structured signal context from validated hypothesis (direction bias, scores, EV, memory/contradiction info)
- `EntryPlanner` — produces entry zones (LIMIT_ZONE, BREAKOUT_CONFIRMATION, PULLBACK, RECLAIM, RETEST) or NO_SAFE_ENTRY
- `StopPlanner` — structure/volatility/liquidity/time-based stop placement with distance calculation
- `TargetPlanner` — TP1/TP2/TP3 based on RR requirements with target realism scoring
- `RRAnalyzer` — enforces minimum 1:3, preferred 1:5 RR with detailed summary
- `ExecutionConditionBuilder` — 5 conditions (validation, no-trade, EV, risk, uncertainty) with REQUIRED/WARNING/BLOCKER types
- `CancellationRuleBuilder` — 8 cancellation rules (price move, invalidation, spread, volatility, no-trade, contradiction, validation, expiry)
- `PositionSizer` — base 1% risk reduced for uncertainty, contradiction, weak memory, high risk; position size from equity
- `SignalQualityScorer` — grades A_PLUS/A/B/C/REJECT with strengths/weaknesses
- `SignalGate` — 9-gate check: validation, EV, confidence, risk, uncertainty, RR, safe entry, quality, conditions; never approves live trading
- `SignalReport` — final recommendation: ALERT_ONLY, PAPER_TRADE_CANDIDATE, REJECT_SIGNAL, WAIT_FOR_ENTRY, NO_SAFE_ENTRY, HUMAN_REVIEW
- Event bus integration: SIGNAL_CANDIDATE_CREATED, SIGNAL_REJECTED, LIVE_TRADE_BLOCKED

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
