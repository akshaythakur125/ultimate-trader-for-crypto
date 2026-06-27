from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from ultimate_trader.storage.database import Base


class MarketSnapshotModel(Base):
    __tablename__ = "market_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    funding_rate = Column(Float, nullable=True)
    open_interest = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)
    volatility = Column(Float, nullable=True)
    orderbook_imbalance = Column(Float, nullable=True)
    liquidation_intensity = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class RegimeAssessmentModel(Base):
    __tablename__ = "regime_assessments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    regime_label = Column(String(50), nullable=False)
    trend_strength = Column(Float, nullable=False)
    volatility_state = Column(String(50), nullable=False)
    compression_score = Column(Float, nullable=False)
    manipulation_risk = Column(Float, nullable=False)
    no_trade_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class LiquidityAssessmentModel(Base):
    __tablename__ = "liquidity_assessments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    equal_highs_detected = Column(Boolean, default=False)
    equal_lows_detected = Column(Boolean, default=False)
    sweep_detected = Column(Boolean, default=False)
    fakeout_detected = Column(Boolean, default=False)
    liquidity_bias = Column(String(20), nullable=True)
    key_liquidity_levels = Column(Text, nullable=True)
    manipulation_score = Column(Float, default=0.0)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class OrderFlowAssessmentModel(Base):
    __tablename__ = "orderflow_assessments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    orderflow_bias = Column(String(20), nullable=True)
    volume_expansion_score = Column(Float, default=0.0)
    funding_bias = Column(String(20), nullable=True)
    open_interest_signal = Column(String(20), nullable=True)
    orderbook_imbalance = Column(Float, nullable=True)
    liquidation_pressure = Column(Float, nullable=True)
    confirmation_score = Column(Float, default=0.0)
    warning_flags = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TradingHypothesisModel(Base):
    __tablename__ = "trading_hypotheses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    hypothesis_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    edge_theory = Column(Text, nullable=False)
    expected_market_regime = Column(String(50), nullable=False)
    required_liquidity_condition = Column(Text, nullable=False)
    required_orderflow_condition = Column(Text, nullable=False)
    expected_holding_time_hours = Column(Float, nullable=False)
    minimum_rr = Column(Float, nullable=False)
    preferred_rr = Column(Float, nullable=False)
    entry_logic_description = Column(Text, nullable=False)
    invalidation_logic_description = Column(Text, nullable=False)
    expected_failure_conditions = Column(Text, nullable=False)
    status = Column(String(20), default="DRAFT")
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class IntelligenceDecisionModel(Base):
    __tablename__ = "intelligence_decisions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String(50), unique=True, nullable=False, index=True)
    symbol = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    bias = Column(String(20), nullable=False)
    long_probability = Column(Float, nullable=False)
    short_probability = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    uncertainty_score = Column(Float, nullable=False)
    trade_quality_score = Column(Float, nullable=False)
    reasoning_summary = Column(Text, nullable=False)
    invalidation_level = Column(Float, nullable=True)
    requires_human_review = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SignalCandidateModel(Base):
    __tablename__ = "signal_candidates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String(50), unique=True, nullable=False, index=True)
    symbol = Column(String(50), nullable=False)
    exchange = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit_1 = Column(Float, nullable=False)
    take_profit_2 = Column(Float, nullable=True)
    take_profit_3 = Column(Float, nullable=True)
    estimated_rr = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    expected_holding_time_hours = Column(Float, nullable=False)
    status = Column(String(20), default="CANDIDATE")
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SignalExplanationModel(Base):
    __tablename__ = "signal_explanations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String(50), unique=True, nullable=False, index=True)
    core_reason = Column(Text, nullable=False)
    confirmations = Column(Text, nullable=True)
    contradictions = Column(Text, nullable=True)
    invalidation = Column(Text, nullable=False)
    risk_notes = Column(Text, nullable=True)
    why_trade_is_allowed = Column(Text, nullable=False)
    what_would_cancel_trade = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class BacktestSummaryModel(Base):
    __tablename__ = "backtest_summaries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    hypothesis_id = Column(String(50), nullable=False, index=True)
    total_trades = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    average_rr = Column(Float, default=0.0)
    expectancy = Column(Float, default=0.0)
    max_drawdown_percent = Column(Float, default=0.0)
    max_daily_drawdown_percent = Column(Float, default=0.0)
    profit_factor = Column(Float, nullable=True)
    false_signal_rate = Column(Float, nullable=True)
    passed = Column(Boolean, default=False)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class LearningReportModel(Base):
    __tablename__ = "learning_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(50), unique=True, nullable=False, index=True)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    best_regimes = Column(Text, nullable=True)
    worst_regimes = Column(Text, nullable=True)
    best_symbols = Column(Text, nullable=True)
    worst_symbols = Column(Text, nullable=True)
    best_time_windows = Column(Text, nullable=True)
    failed_patterns = Column(Text, nullable=True)
    recommended_changes = Column(Text, nullable=True)
    warnings = Column(Text, nullable=True)
    requires_human_approval = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TradeJournalModel(Base):
    __tablename__ = "trade_journal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(50), unique=True, nullable=False, index=True)
    signal_id = Column(String(50), nullable=False)
    symbol = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=False)
    take_profit_1 = Column(Float, nullable=False)
    take_profit_2 = Column(Float, nullable=True)
    take_profit_3 = Column(Float, nullable=True)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    r_multiple = Column(Float, nullable=True)
    status = Column(String(20), default="PENDING")
    hypothesis_id = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
