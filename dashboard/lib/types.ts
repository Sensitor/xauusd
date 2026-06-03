/**
 * TypeScript types mirroring the GoldMind FastAPI contract.
 *
 * These intentionally track `goldmind.core.schemas` / `goldmind.core.enums`
 * on the backend so the two stay in lockstep. String-literal unions mirror the
 * server's StrEnum values exactly (JSON-friendly, human-readable).
 */

// ---------------------------------------------------------------------------
// Enums (string literals matching the backend StrEnum values)
// ---------------------------------------------------------------------------
export type Environment = "dev" | "staging" | "prod";
export type ExecutionMode = "shadow" | "semi_auto" | "full_auto";

export type Bias = "bullish" | "bearish" | "neutral";
export type TradeDecisionType = "BUY" | "SELL" | "NO_TRADE";

export type TrendRegime = "trending_up" | "trending_down" | "ranging";
export type PhaseRegime = "expansion" | "compression";
export type VolatilityRegime = "high" | "normal" | "low";
export type RiskEnvironment = "risk_on" | "risk_off" | "neutral";

export type OrderSide = "buy" | "sell";
export type TradeStatus =
  | "proposed"
  | "pending"
  | "open"
  | "closed"
  | "cancelled"
  | "rejected";

export type Severity = "info" | "warning" | "critical";

/** Stable agent identifiers — used as keys, labels, and weight map fields. */
export type AgentName =
  | "market_structure"
  | "technical"
  | "macro"
  | "news_sentiment"
  | "chart_vision"
  | "market_regime"
  | "risk_manager"
  | "decision_engine"
  | "execution"
  | "learning";

/** The six agents that contribute a directional/quality vote. */
export const SCORING_AGENTS: AgentName[] = [
  "market_structure",
  "technical",
  "macro",
  "news_sentiment",
  "chart_vision",
  "market_regime",
];

/** All ten agents in canonical display order. */
export const ALL_AGENTS: AgentName[] = [
  "market_structure",
  "technical",
  "macro",
  "news_sentiment",
  "chart_vision",
  "market_regime",
  "risk_manager",
  "decision_engine",
  "execution",
  "learning",
];

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------
export interface RiskFlag {
  code: string;
  message: string;
  severity: Severity;
  source?: AgentName | null;
}

export interface AgentOutput {
  agent: AgentName;
  bias: Bias;
  confidence: number; // [0, 1]
  reasoning: string;
  risk_flags: RiskFlag[];
  /** Structured, agent-specific detail (only present on /decisions/{id}). */
  analysis?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// GET /health
// ---------------------------------------------------------------------------
export interface HealthResponse {
  status: string;
  environment: Environment;
  execution_mode: ExecutionMode;
}

// ---------------------------------------------------------------------------
// GET /config
// ---------------------------------------------------------------------------
export interface RiskConfig {
  max_risk_per_trade: number;
  max_daily_drawdown: number;
  max_total_drawdown: number;
  max_consecutive_losses: number;
  max_trades_per_day: number;
  min_reward_risk: number;
}

export interface DecisionWeights {
  market_structure: number;
  technical: number;
  macro: number;
  news_sentiment: number;
  chart_vision: number;
  market_regime: number;
  risk_manager: number;
}

export interface ConfigResponse {
  symbol: string;
  execution_mode: ExecutionMode;
  risk: RiskConfig;
  weights: DecisionWeights;
}

// ---------------------------------------------------------------------------
// Decision Engine / sizing
// ---------------------------------------------------------------------------
export interface AgentVote {
  agent: AgentName;
  bias: Bias;
  confidence: number;
  weight: number;
  /** weight * signed_confidence — the agent's push on the net score. */
  contribution: number;
}

export interface TakeProfit {
  price: number;
  r_multiple: number;
  close_fraction: number;
}

export interface PositionSizing {
  side: OrderSide;
  entry: number;
  stop_loss: number;
  take_profits: TakeProfit[];
  lot_size: number;
  risk_amount: number;
  risk_pct: number;
  reward_risk: number;
  break_even_price?: number | null;
  trailing_distance?: number | null;
}

export interface TradingDecision {
  id: string;
  symbol: string;
  decision: TradeDecisionType;
  bias: Bias;
  confidence: number; // [0, 1]
  quality_score: number; // [0, 100]
  net_directional_score: number; // [-1, 1]
  agreement: number; // [0, 1]
  reasoning: string;
  votes: AgentVote[];
  risk_flags: RiskFlag[];
  sizing?: PositionSizing | null;
}

// ---------------------------------------------------------------------------
// GET /regime  (and embedded in /evaluate)
// ---------------------------------------------------------------------------
export interface MarketRegime {
  trend_regime: TrendRegime;
  phase_regime: PhaseRegime;
  volatility_regime: VolatilityRegime;
  adx: number | null;
  quality_multiplier: number;
  recommended_behavior: string;
}

// ---------------------------------------------------------------------------
// POST /evaluate
// ---------------------------------------------------------------------------
export interface EvaluationResult {
  decision: TradingDecision;
  regime: MarketRegime;
  agents: AgentOutput[];
}

export interface EvaluateRequest {
  synthetic?: boolean;
}

// ---------------------------------------------------------------------------
// GET /decisions  /  GET /decisions/{id}
// ---------------------------------------------------------------------------
export interface DecisionSummary {
  id: string;
  decision: TradeDecisionType;
  bias: Bias;
  confidence: number;
  quality_score: number;
  net_score: number;
  agreement: number;
  created_at: string; // ISO timestamp
}

export interface DecisionDetail {
  signal: TradingDecision;
  agent_outputs: AgentOutput[];
}

// ---------------------------------------------------------------------------
// GET /trades  /  GET /trades/active
// ---------------------------------------------------------------------------
export interface Trade {
  id: string;
  side: OrderSide;
  status: TradeStatus;
  volume: number;
  entry_price: number;
  stop_loss: number | null;
  exit_price: number | null;
  pnl: number | null;
  r_multiple: number | null;
  reward_risk: number | null;
  opened_at: string | null; // ISO timestamp
  closed_at: string | null; // ISO timestamp
}

// ---------------------------------------------------------------------------
// GET /performance
// ---------------------------------------------------------------------------
export interface LearningInsight {
  category: string; // 'filter' | 'risk' | 'selection' | 'regime'
  statement: string;
  confidence: number;
}

export interface PerformanceReport {
  window_start: string; // ISO timestamp
  window_end: string; // ISO timestamp
  trades: number;
  win_rate: number; // [0, 1]
  profit_factor: number;
  expectancy_r: number;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown_pct: number | null; // [0, 1]
  max_drawdown_r: number | null;
  avg_win_r: number | null;
  avg_loss_r: number | null;
  best_conditions: Record<string, unknown>;
  worst_conditions: Record<string, unknown>;
  insights: LearningInsight[];
}

// ---------------------------------------------------------------------------
// GET /news
// ---------------------------------------------------------------------------
export interface NewsItem {
  title: string;
  source: string;
  importance: Severity; // info/warning/critical ~ low/med/high impact
  scheduled_at: string | null; // ISO timestamp
  sentiment: number; // [-1, 1]
  url: string | null;
}

// ---------------------------------------------------------------------------
// Derived / UI-only shapes
// ---------------------------------------------------------------------------
export interface EquityPoint {
  /** ISO timestamp or trade index label. */
  t: string;
  /** Cumulative equity in account currency. */
  equity: number;
  /** Cumulative return in R units. */
  r: number;
}
