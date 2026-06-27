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
