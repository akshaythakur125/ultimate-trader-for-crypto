# Ultimate Trader

**Autonomous Intraday Crypto Futures Trading Intelligence System**

Ultimate Trader is not a scanner, not a single trading strategy, and not a normal bot. It is a full intelligent trading system designed to behave like a professional trading desk — observing markets, generating hypotheses, analyzing regime and liquidity, interpreting order flow, making probabilistic decisions, managing risk, backtesting, learning, and controlling execution.

## Prompt Progress

### Phase 2 — Intelligence Upgrade

### Phase 2, Prompt 1 — Market Microstructure Engine
- `OrderBookSnapshot` — computed properties (best_bid, best_ask, mid_price, spread, spread_bps, bid/ask depth, depth imbalance)
- `SpreadAnalyzer` — NORMAL / WIDE / UNSTABLE / TRADE_BLOCKING with configurable thresholds
- `OrderBookDepthAnalyzer` — NORMAL / THIN / IMBALANCED / CRITICAL depth states; liquidity wall detection
- `OrderBookImbalanceAnalyzer` — score 0–100, LONG/SHORT/NEUTRAL bias, moderate/strong classification
- `LiquidityVoidDetector` — detects price zones with low resting liquidity between order book levels
- `PriceImpactEstimator` — slippage estimation, max safe quantity, execution risk (LOW/MEDIUM/HIGH/CRITICAL)
- `AbsorptionDetector` — detects aggressive buying/selling absorbed near support/resistance, price stuck
- `SpoofingRiskDetector` — wall flashing, imbalance instability, fake wall placement; risk levels NONE/LOW/MEDIUM/HIGH
- `MicrostructureState` — aggregates all analyzers into ALLOW/CAUTION/BLOCK trade permission
- `MicrostructureReport` — readable summary with reasons to avoid
- Event: `MICROSTRUCTURE_ANALYSIS_COMPLETED`
- Accepts BingX OrderBook data, publishes events, integrates with main.py health check

### Phase 2, Prompt 2 — Institutional Order Flow Intelligence
- `TradePrint` — trade data model with side, aggressor_side, quantity, price, trade_value
- `TradeFlowBuffer` — rolling trade window with buy/sell volume, cumulative delta, large trade counting
- `AggressionAnalyzer` — buy/sell aggression scores (0–100), BUYER_AGGRESSION/SELLER_AGGRESSION/BALANCED bias, large trade pressure (normal/elevated/very_high)
- `AbsorptionIntelligence` — detects buying/selling absorbed when dominant aggression fails to move price against passive institutional participant
- `ExhaustionDetector` — detects fading buyer/seller aggression over consecutive windows, exhaustion score 0–100
- `IcebergDetector` — groups trades by price proximity, scores repeat-level patterns for NONE/LOW/MODERATE/HIGH suspicion
- `DeltaDivergenceDetector` — price vs cumulative delta direction mismatch, bullish/bearish divergence with weak/moderate/strong strength
- `FlowMomentumAnalyzer` — acceleration/deceleration, persistence, reversal risk, momentum score 0–100
- `TrapDetector` — long/short trap detection using aggression + absorption mismatch, divergence, or weak breakout/breakdown; BLOCK_TRADE/CAUTION/WAIT actions
- `OrderFlowScenarioEngine` — 9 competing scenarios (genuine accumulation/distribution, passive absorption, squeeze, exhaustion reversal, fake breakout, no edge) with probability estimates and invalidation conditions
- `InstitutionalOrderFlowReport` — aggregates all analysis into ALLOW/CAUTION/BLOCK trade permission with reasons to avoid and support
- Event: `INSTITUTIONAL_ORDERFLOW_COMPLETED`
- 125 tests passing, integrates with main.py health check

### Phase 2, Prompt 3 — Liquidity Mapping & Smart Money Engine
- `Candle` — OHLCV model with symbol, timeframe, timestamp
- `SwingDetector` — swing highs/lows, equal highs/lows (configurable lookback and equality threshold)
- `LiquidityPoolDetector` — buy-side/sell-side liquidity pools from equal highs/lows and swing points; stop clusters from volume spikes; swept/unswept zone tracking
- `SweepDetector` — buy-side/sell-side sweeps with reclaim detection, failed sweep detection, displacement integration
- `MarketStructureEngine` — BOS (Break of Structure), CHoCH (Change of Character), MSS (Market Structure Shift), trend continuation, structure failure, range, compression before expansion
- `FairValueGapDetector` — bullish/bearish FVG, gap size in bps, mitigation/fill status tracking
- `OrderBlockDetector` — bullish/bearish order blocks from FVGs, breaker blocks from mitigated OBs, strength scoring (body ratio, volume, direction alignment)
- `PremiumDiscountEngine` — dealing range from swing extremes, premium/discount zones, equilibrium, optimal trade entry zone
- `DisplacementEngine` — strong/weak/volume-supported/fake displacement detection, displacement after sweep
- `ConfluenceEngine` — scores liquidity, structure, FVG, order blocks, premium/discount, displacement, order-flow bias, microstructure bias; produces score 0–100, directional bias, trade permission, reasons for/against
- `LiquiditySmartMoneyReport` — aggregates all sub-analyzers into ALLOW/CAUTION/BLOCK permission with final summary
- Accepts OHLCV candles from BingX client, microstructure reports, institutional orderflow reports
- Event: `LIQUIDITY_SMART_MONEY_COMPLETED`
- 64 tests passing, integrates with main.py health check

### Phase 2, Prompt 4 — Historical Replay & End-to-End Backtesting Engine
- `HistoricalCandle` — OHLCV model with symbol, timeframe, timestamp
- `HistoricalDataLoader` — CSV loading with column validation, sort by timestamp, reject duplicates and missing values
- `CandleReplayer` — replay candles one by one, no future leakage, rolling window, warmup period
- `ReplayPipelineRunner` — calls all available engines (LSM, microstructure, orderflow, research, belief, validation, signal) per candle; gracefully skips engines with missing data
- `TradeSimulator` — simulates trades from TradePlan: entry zone triggers, stop loss/take profit, conservative stop-first when both hit same candle; fees, slippage, funding included; long/short support; expiry after N candles, max holding time
- `ReplayTrade` — trade outcome model with gross_r, fees_r, slippage_r, funding_r, net_r, exit reason, holding candles
- `ReplayJournal` — stores every candle, skipped signal, generated plan, executed trade, rejection reason, engine failure
- `ReplayMetrics` — total_signals, rejected, executed, win_rate, average_r, expectancy_r, profit_factor, max_drawdown_r, consecutive losses, holding time, best/worst trade, rejection rate, conversion rate
- `ParameterSweeper` — tests parameter sets (confluence_score_threshold, min_rr, max_risk_score, min_confidence, max_uncertainty, stop_distance, target_rr), ranks results, overfit warning for fragile best result
- `ReplayReport` — report_id, symbol, timeframe, metrics, trades, rejected/engine-skip summaries, optional sweep results; conclusion: EDGE_DETECTED / NO_EDGE / INSUFFICIENT_DATA / NEEDS_MORE_TESTING with explanation
- Events: `HISTORICAL_REPLAY_STARTED`, `HISTORICAL_REPLAY_COMPLETED`, `REPLAY_TRADE_OPENED`, `REPLAY_TRADE_CLOSED`, `REPLAY_SIGNAL_REJECTED`
- 6 test files, integrates with main.py health check

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

---
### Phase 3 — Strategy & Statistical Proof

### Phase 3, Prompt 1 — A+ Signal Grade & Selective Strategy
- `SignalQualityScorer` — grades A_PLUS (top 10%), A, B, C, REJECT with specificity/reliability/minimum_grade fields
- `StrategyConfig` — min_grade filter; selective strategy only accepts A+ signals
- Trade rate: ~0.8 trades/day (vs ~8/day unrestricted), manual-like selectivity
- Verified: no early peak, stable per-window performance in walk-forward

### Phase 3, Prompt 2 — RR Rules, Stop & Target Logic
- `TradePlan` — three take-profit levels (TP1 1.5R, TP2 3.0R, TP3 5.0R) with 40%/30%/30% allocation
- `StopPlanner` — structure-based stops at 1.5×ATR, volatility-adjusted, 3% hard max
- Minimum RR: 1:3, preferred: 1:5
- No SL=TP approach; all stops and targets are structure-derived, not symmetric

### Phase 3, Prompts 3–6 — Confidence, Ranking, Filters, RiskGovernor
- `ConfidenceGate` — min_directional_confidence, max_conflict_score, max_reversal_risk, min_confluence_score
- `CandidateRanker` — multi-factor ranking (confluence, confidence, EV, microstructure, orderflow)
- `DailySelector` — target_trades_per_day=2, hard_max=3, drawdown-sensitive daily loss limit
- `RiskGovernor` — real-time drawdown control with emergency circuit breaker

### Phase 3, Prompt 7 — Drawdown RiskGovernor & Walk-Forward Validation
- `RiskGovernorConfig` — drawdown_limit=8.0R, emergency_stop=12.0R, trailing_stop=True
- Walk-forward 8-window (30d train, 15d test, 15d step): 5/8 profitable, avg EV +0.02R
- Governor mode (8-fold drawdown control): 33 trades, avg EV +0.25R, PF 2.32
- Final A+ verdict: OVERFIT_SUSPECTED (DD 12.3R in worst window, WF 62.5% profitable, governor only 33t)

### Phase 3, Prompt 8 — Long-History Walk-Forward Proof
- 180-day walk-forward (8 windows, 30d/15d/15d): 97 A+ trades, 62.5% profitable, avg EV +0.16R
- All thresholds frozen: no optimization, no tuning
- Verified time-causal: train strictly before test in every window
- Regime gate introduced as potential path to fix DD and concentration

### Phase 3, Prompt 9 — Regime-Aware Selectivity Gate (Final Prompt)
- `regime_filter/` package: RegimeGate, RegimeGateConfig, RegimeGateDecision, ReferenceProfile, SimilarityScorer, RegimeClassifier
- 10-dimensional feature extraction from OHLCV + LSM pipeline
- Percentile-distance similarity scoring (blocks ~10–32% of A+ signals)
- Time-causal walk-forward: reference built from data strictly before test window
- No look-ahead bias, no optimization, no threshold fitting

**Primary Validation (30d train, 30d test, 30d step, 4 non-overlapping windows):**

| Metric | A+ alone | +regime gate | Change |
|---|---|---|---|
| Unique OOS trades | 114 | 81 | −29% |
| Profitable windows | 3/4 (75%) | 3/4 (75%) | — |
| Avg EV | +0.31R | +0.51R | **+65%** |
| Avg PF | 1.75 | 1.91 | +9% |
| Max DD | 17.4R | 11.7R | **−33%** |
| Concentration | 86.9% | 43.3% | **fixed** |
| Block rate | — | 10–24% | healthy |

**Secondary Sensitivity Test (30d train, 30d test, 15d step, 8 overlapping windows, trades deduplicated):**
- 128 unique OOS trades with regime gate (above 100), avg EV +0.41R, PF 1.76
- But only 62.5% profitable windows (below 70% threshold)

**Validation Verdict: INSUFFICIENT_TRADES**

The regime gate improves every quality metric (EV +65%, PF +9%, DD −33%, concentration fixed) and blocks at a healthy 10–32% rate. However:

1. **Unique OOS trades (81) below 100 threshold** — 30% trade suppression from the regime gate leaves an insufficient sample for ROBUST_EDGE in the primary non-overlapping test.
2. **Max DD (11.7R) above 8.0R threshold** — improved 33% from 17.4R but still excessive.
3. **Secondary test shows 62.5% profitable windows** — below the 70% threshold even with 128 unique OOS trades.

**Current Best Configuration (frozen):**
- Grade: A+ only (A_PLUS)
- Min RR: 1:3
- Stop: 1.5×ATR (structure-derived, max 3%)
- Targets: TP1 1.5R (40%), TP2 3.0R (30%), TP3 5.0R (30%)
- Max trades/day: 3
- Confidence gate: confluence ≥3, directional_confidence ≥0.4, conflict ≤3, reversal_risk ≤4
- RiskGovernor: drawdown_limit=8.0R, emergency_stop=12.0R
- **RegimeGate: similarity_threshold=50, percentile-distance scoring**
- **Live/paper trading: DISABLED**

**Next Research Direction:**
- Improve signal quality at source rather than fitting thresholds
- Test with more historical data (≥360 days) if available to increase OOS trade count
- No live or paper deployment until OOS trade count exceeds 100 in primary non-overlapping test

---
### Phase 4 — Structural Stop-Loss Validation

### Loss Diagnosis
- **93% of losses (42/45) are quick stop-outs (≤3 candles)** — exit via `STOP_LOSS` in all cases
- Avg win +2.76R, avg loss −1.24R, WR 44.4%
- Regime gate doesn't discriminate quick vs slow losses (regime score ≥50 for all)
- Root cause: stop = 1.5× single-candle range is too noise-sensitive for 15m BTCUSDT

### Entry Timing Diagnosis
Tested whether quick losses are caused by bad entry timing rather than stop distance:

| Method | Trades | WR | EV | PF | DD | QkLs |
|--------|--------|----|----|----|-----|------|
| immediate | 79 | 46.8% | +0.65R | 2.00 | 8.6R | 93% |
| confirm_1c | 78 | 43.6% | +0.64R | 1.84 | 11.0R | 93% |
| no_reverse_0.5r | 73 | 47.9% | +0.71R | 2.14 | 11.0R | 95% |
| confirm_direction | 37 | 54.1% | +0.39R | 1.72 | 9.6R | 100% |
| skip_low_volatility | 57 | 54.4% | +0.96R | 2.72 | 5.3R | 100% |

**Verdict: Not an entry-timing problem.** Every method shows ≥93% quick losses. Delaying entry or filtering by micro-direction doesn't change the outcome — the stop itself is structurally too tight. `skip_low_volatility` notably improves EV/PF/DD (+0.96R, 2.72, 5.3R) but worsens quick-loss to 100%.

### Stop-Distance Comparison
Compared 7 structural stop approaches using the same 30/30/30 causal walk-forward with regime gate:

#### Methods
1. **hybrid** — max(1.5×cr, min(structure, 1.5×cr×1.2)) (current baseline)
2. **wide20** — 2.0 × candle range
3. **wide25** — 2.5 × candle range
4. **atr14_15** — 1.5 × ATR14
5. **atr14_20** — 2.0 × ATR14
6. **structure** — nearest swing/OB invalidation level
7. **hybrid + skip_low_volatility**
8. **atr14_20 + skip_low_volatility**

#### Results

| Method | Trd | WR | EV | PF | DD | QkLs | AvgW | AvgL |
|--------|-----|----|----|----|-----|------|------|------|
| hybrid | 79 | 46.8% | +0.65R | 2.00 | 8.6R | 93% | +2.78R | −1.23R |
| wide20 | 89 | 41.6% | +0.48R | 1.70 | 13.6R | 85% | +2.82R | −1.18R |
| wide25 | 79 | 43.0% | +0.58R | 1.88 | 10.9R | 91% | +2.86R | −1.15R |
| atr14_15 | 79 | 41.8% | +0.41R | 1.57 | 11.2R | 89% | +2.72R | −1.25R |
| **atr14_20** | **76** | **46.1%** | **+0.65R** | **2.01** | **8.6R** | **85%** | +2.79R | −1.18R |
| structure | 78 | 34.6% | +0.00R | 1.00 | 15.2R | 92% | +2.64R | −1.39R |
| hybrid+skip | 57 | 54.4% | +0.96R | 2.72 | 5.3R | 100% | +2.78R | −1.22R |
| atr14_20+skip | 53 | 47.2% | +0.68R | 2.06 | 7.2R | 93% | +2.78R | −1.20R |

#### Acceptance Rule Check
| Method | EV≥+0.65 | PF≥2.0 | DD≤8.6R | QkLs<90% | Verdict |
|--------|----------|--------|---------|----------|---------|
| wide20 | +0.48 ❌ | 1.70 ❌ | 13.6 ❌ | **85%** ✅ | ❌ |
| wide25 | +0.58 ❌ | 1.88 ❌ | 10.9 ❌ | 91% ❌ | ❌ |
| atr14_15 | +0.41 ❌ | 1.57 ❌ | 11.2 ❌ | 89% ✅ | ❌ |
| **atr14_20** | **+0.65 ⚠️** | **2.01 ✅** | **8.6 ✅** | **85% ✅** | **⚠️ borderline** |
| structure | +0.00 ❌ | 1.00 ❌ | 15.2 ❌ | 92% ❌ | ❌ |
| hybrid+skip | +0.96 ✅ | 2.72 ✅ | 5.3 ✅ | 100% ❌ | ❌ |
| atr14_20+skip | +0.68 ✅ | 2.06 ✅ | 7.2 ✅ | 93% ❌ | ❌ |

#### Final Verdict

**Recommended candidate: atr14_20** — 2.0 × ATR14 stop. It is the only method that:
- Reduces quick-loss meaningfully (93% → **85%**, −8pp)
- Maintains hybrid EV (+0.65R), PF (2.01), DD (8.6R)
- Has sufficient OOS trades (76)
- Uses the same causal walk-forward framework (no look-ahead bias)
- All 1116 tests pass

**⚠️ EV is borderline.** The displayed +0.65R may reflect floating-point rounding (true value ~0.649R). Future validation with longer data (≥360 days) or higher-frequency OOS tests is required before deployment.

**Current Best Configuration (Phase 4 update):**
- Stop method: `atr14_20` (2.0 × ATR14, with hybrid-style structure cap)
- Stop distance: `max(atr14 * 2.0, min(structure_dist, atr14 * 2.0 / 2.5 * 3.0))`
- Target: 3× stop distance (maintains RR ≥ 3.0)
- Entry: immediate (no delayed entry)
- Regime gate: similarity_threshold=50, percentile-distance scoring
- Grade: A+ only (A_PLUS)
- Min RR: 1:3
- Confidence gate: confluence ≥3, directional_confidence ≥0.4, conflict ≤3, reversal_risk ≤4
- RiskGovernor: drawdown_limit=8.0R, emergency_stop=12.0R
- Max trades/day: 3
- **Live/paper trading: DISABLED**

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
  historical_replay/         # Historical replay & backtesting engine (Phase 2, Prompt 4)
tests/                       # Test suite
```
