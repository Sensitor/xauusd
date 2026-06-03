/**
 * Realistic mock data so the dashboard renders standalone (no backend).
 *
 * Numbers track the backend defaults: decision weights sum to 1.0 and the risk
 * limits match `goldmind.config.RiskConfig`. The api client falls back to these
 * payloads whenever the FastAPI service is unreachable.
 */
import type {
  AgentOutput,
  ConfigResponse,
  DecisionDetail,
  DecisionSummary,
  EquityPoint,
  EvaluationResult,
  HealthResponse,
  MarketRegime,
  NewsItem,
  PerformanceReport,
  Trade,
  TradingDecision,
} from "./types";

// Anchor "now" so relative times in the UI look sensible without a backend.
const NOW = new Date("2026-06-03T14:30:00Z");
const iso = (offsetMin: number) =>
  new Date(NOW.getTime() + offsetMin * 60_000).toISOString();

export const mockHealth: HealthResponse = {
  status: "ok",
  environment: "dev",
  execution_mode: "shadow",
};

export const mockConfig: ConfigResponse = {
  symbol: "XAUUSD",
  execution_mode: "shadow",
  risk: {
    max_risk_per_trade: 0.005,
    max_daily_drawdown: 0.02,
    max_total_drawdown: 0.06,
    max_consecutive_losses: 3,
    max_trades_per_day: 5,
    min_reward_risk: 1.8,
  },
  weights: {
    market_structure: 0.25,
    technical: 0.2,
    macro: 0.2,
    news_sentiment: 0.1,
    chart_vision: 0.1,
    market_regime: 0.1,
    risk_manager: 0.05,
  },
};

export const mockRegime: MarketRegime = {
  trend_regime: "trending_up",
  phase_regime: "expansion",
  volatility_regime: "high",
  adx: 31.4,
  quality_multiplier: 0.9,
  recommended_behavior:
    "Trend is established and volatility is expanding. Favor continuation setups in the direction of H4 structure; widen stops to account for elevated ATR and avoid mean-reversion entries until the impulse exhausts.",
};

// ---------------------------------------------------------------------------
// Agents (10) — analytical outputs.
// ---------------------------------------------------------------------------
export const mockAgents: AgentOutput[] = [
  {
    agent: "market_structure",
    bias: "bullish",
    confidence: 0.78,
    reasoning:
      "H4 and H1 in confirmed uptrend with a recent break of structure above 2,348. Price is mitigating a bullish H1 order block at 2,331–2,335 after sweeping sellside liquidity. MTF alignment strongly bullish (0.71).",
    risk_flags: [
      {
        code: "premium_pricing",
        message: "Price entering premium of the H4 dealing range (0.68).",
        severity: "info",
        source: "market_structure",
      },
    ],
    analysis: {
      structural_bias: "bullish",
      mtf_alignment: 0.71,
      premium_discount: 0.68,
    },
  },
  {
    agent: "technical",
    bias: "bullish",
    confidence: 0.64,
    reasoning:
      "Momentum positive: H1 RSI 61 and rising, MACD histogram expanding above zero, price above EMA20/50/200 stack. Indicator alignment 0.66. Watch for short-term RSI divergence on M15.",
    risk_flags: [],
    analysis: {
      bullish_bearish_score: 0.42,
      indicator_alignment_score: 0.66,
      momentum_score: 0.38,
    },
  },
  {
    agent: "macro",
    bias: "bullish",
    confidence: 0.58,
    reasoning:
      "DXY rolling over and US10Y yields easing after softer-than-expected CPI surprise (-0.2). Risk-off undertone supports gold as a haven. Net macro tailwind, moderate conviction.",
    risk_flags: [],
    analysis: {
      macro_bias: "bullish",
      risk_environment: "risk_off",
      dxy_trend: "bearish",
      yields_trend: "bearish",
    },
  },
  {
    agent: "news_sentiment",
    bias: "neutral",
    confidence: 0.4,
    reasoning:
      "Aggregate headline sentiment mildly positive (+0.18). However FOMC press conference is 95 minutes out — a high-impact event. Approaching the pre-event blackout window; size and timing should respect event risk.",
    risk_flags: [
      {
        code: "high_impact_news_window",
        message: "FOMC press conference in ~95m (high impact).",
        severity: "warning",
        source: "news_sentiment",
      },
    ],
    analysis: {
      sentiment_score: 0.18,
      minutes_to_next_high_impact: 95,
      in_blackout_window: false,
    },
  },
  {
    agent: "chart_vision",
    bias: "bullish",
    confidence: 0.55,
    reasoning:
      "Vision model reads an ascending-triangle continuation on H1 with resistance near 2,352 and rising support. No bearish reversal patterns detected. Key risk area: failure to hold 2,338.",
    risk_flags: [],
    analysis: {
      detected_trend: "bullish",
      support_levels: [2338, 2331],
      resistance_levels: [2352, 2360],
    },
  },
  {
    agent: "market_regime",
    bias: "bullish",
    confidence: 0.62,
    reasoning:
      "ADX 31.4 confirms a trending regime; Bollinger/ATR phase is expansion with high volatility. Regime favors trend-continuation and warrants a slightly permissive quality bar (multiplier 0.90).",
    risk_flags: [
      {
        code: "elevated_volatility",
        message: "Volatility regime HIGH — widen stops, expect larger swings.",
        severity: "info",
        source: "market_regime",
      },
    ],
    analysis: {
      trend_regime: "trending_up",
      phase_regime: "expansion",
      volatility_regime: "high",
      adx: 31.4,
      quality_multiplier: 0.9,
    },
  },
  {
    agent: "risk_manager",
    bias: "neutral",
    confidence: 0.7,
    reasoning:
      "Account within all limits: drawdown 1.1% of 6% cap, 1 trade today of 5, no consecutive-loss pressure. Proposed setup meets the 1.8 minimum reward:risk (blended 2.31). Approved with 0.40 lots risking 0.50% of equity.",
    risk_flags: [],
    analysis: {
      approved: true,
      circuit_breaker_active: false,
    },
  },
  {
    agent: "decision_engine",
    bias: "bullish",
    confidence: 0.72,
    reasoning:
      "Weighted vote net directional score +0.46 with 0.82 voter agreement. Quality score 71/100 clears the regime-adjusted threshold. No critical risk flags. Verdict: BUY.",
    risk_flags: [],
    analysis: {
      decision: "BUY",
      net_directional_score: 0.46,
      agreement: 0.82,
      quality_score: 71,
    },
  },
  {
    agent: "execution",
    bias: "neutral",
    confidence: 0.66,
    reasoning:
      "Shadow mode — no live order routed. Simulated fill at 2,342.10 with 1.2-point slippage and 38ms latency. Spread within tolerance (deviation 20 points).",
    risk_flags: [],
    analysis: {
      mode: "shadow",
      simulated_fill: 2342.1,
      slippage_points: 1.2,
    },
  },
  {
    agent: "learning",
    bias: "neutral",
    confidence: 0.5,
    reasoning:
      "Historical edge in trending_up + high-volatility regimes shows a 61% win rate and 1.92 profit factor over the last 90 days. Continuation longs after a liquidity sweep are the strongest cohort.",
    risk_flags: [],
    analysis: {
      sample_size: 142,
      regime_win_rate: 0.61,
    },
  },
];

// ---------------------------------------------------------------------------
// Latest decision (mirrors what /evaluate returns under `decision`).
// ---------------------------------------------------------------------------
export const mockDecision: TradingDecision = {
  id: "9f1c2a4e-1b6d-4d2a-9f3e-7c2a51d0e001",
  symbol: "XAUUSD",
  decision: "BUY",
  bias: "bullish",
  confidence: 0.72,
  quality_score: 71,
  net_directional_score: 0.46,
  agreement: 0.82,
  reasoning:
    "Multi-timeframe structure is bullish with a fresh break of structure and an unmitigated H1 demand order block. Macro tailwind from a softer CPI and falling DXY aligns with the technical and regime read. Six voters agree (0.82). Quality 71/100 clears the regime-adjusted bar. FOMC in ~95m is the main caveat — position is sized conservatively at 0.50% risk and should be flat or de-risked into the event.",
  votes: [
    { agent: "market_structure", bias: "bullish", confidence: 0.78, weight: 0.25, contribution: 0.195 },
    { agent: "technical", bias: "bullish", confidence: 0.64, weight: 0.2, contribution: 0.128 },
    { agent: "macro", bias: "bullish", confidence: 0.58, weight: 0.2, contribution: 0.116 },
    { agent: "news_sentiment", bias: "neutral", confidence: 0.4, weight: 0.1, contribution: 0.0 },
    { agent: "chart_vision", bias: "bullish", confidence: 0.55, weight: 0.1, contribution: 0.055 },
    { agent: "market_regime", bias: "bullish", confidence: 0.62, weight: 0.1, contribution: 0.062 },
  ],
  risk_flags: [
    {
      code: "high_impact_news_window",
      message: "FOMC press conference in ~95m (high impact). De-risk into the event.",
      severity: "warning",
      source: "news_sentiment",
    },
    {
      code: "elevated_volatility",
      message: "Volatility regime HIGH — stops widened to 1.5x ATR.",
      severity: "info",
      source: "market_regime",
    },
  ],
  sizing: {
    side: "buy",
    entry: 2342.1,
    stop_loss: 2333.4,
    take_profits: [
      { price: 2355.15, r_multiple: 1.5, close_fraction: 0.5 },
      { price: 2363.85, r_multiple: 2.5, close_fraction: 0.3 },
      { price: 2376.9, r_multiple: 4.0, close_fraction: 0.2 },
    ],
    lot_size: 0.4,
    risk_amount: 250.0,
    risk_pct: 0.005,
    reward_risk: 2.31,
    break_even_price: 2350.8,
    trailing_distance: 11.6,
  },
};

export const mockEvaluation: EvaluationResult = {
  decision: mockDecision,
  regime: mockRegime,
  agents: mockAgents,
};

// ---------------------------------------------------------------------------
// Decision history (/decisions).
// ---------------------------------------------------------------------------
export const mockDecisions: DecisionSummary[] = [
  { id: mockDecision.id, decision: "BUY", bias: "bullish", confidence: 0.72, quality_score: 71, net_score: 0.46, agreement: 0.82, created_at: iso(-8) },
  { id: "d2", decision: "NO_TRADE", bias: "neutral", confidence: 0.31, quality_score: 38, net_score: 0.07, agreement: 0.41, created_at: iso(-68) },
  { id: "d3", decision: "SELL", bias: "bearish", confidence: 0.69, quality_score: 67, net_score: -0.44, agreement: 0.78, created_at: iso(-152) },
  { id: "d4", decision: "BUY", bias: "bullish", confidence: 0.74, quality_score: 73, net_score: 0.51, agreement: 0.85, created_at: iso(-241) },
  { id: "d5", decision: "NO_TRADE", bias: "bearish", confidence: 0.45, quality_score: 44, net_score: -0.19, agreement: 0.52, created_at: iso(-372) },
  { id: "d6", decision: "BUY", bias: "bullish", confidence: 0.66, quality_score: 64, net_score: 0.39, agreement: 0.73, created_at: iso(-498) },
  { id: "d7", decision: "SELL", bias: "bearish", confidence: 0.71, quality_score: 70, net_score: -0.48, agreement: 0.8, created_at: iso(-640) },
  { id: "d8", decision: "NO_TRADE", bias: "neutral", confidence: 0.28, quality_score: 33, net_score: 0.03, agreement: 0.38, created_at: iso(-770) },
];

export const mockDecisionDetail: DecisionDetail = {
  signal: mockDecision,
  agent_outputs: mockAgents,
};

// ---------------------------------------------------------------------------
// Trades.
// ---------------------------------------------------------------------------
export const mockTrades: Trade[] = [
  {
    id: "t-101",
    side: "buy",
    status: "open",
    volume: 0.4,
    entry_price: 2342.1,
    stop_loss: 2333.4,
    exit_price: null,
    pnl: 168.0,
    r_multiple: 0.67,
    reward_risk: 2.31,
    opened_at: iso(-7),
    closed_at: null,
  },
  {
    id: "t-100",
    side: "sell",
    status: "open",
    volume: 0.2,
    entry_price: 2351.8,
    stop_loss: 2359.2,
    exit_price: null,
    pnl: -42.0,
    r_multiple: -0.28,
    reward_risk: 2.0,
    opened_at: iso(-95),
    closed_at: null,
  },
  {
    id: "t-099",
    side: "buy",
    status: "closed",
    volume: 0.4,
    entry_price: 2318.6,
    stop_loss: 2310.1,
    exit_price: 2334.9,
    pnl: 652.0,
    r_multiple: 1.92,
    reward_risk: 2.4,
    opened_at: iso(-310),
    closed_at: iso(-205),
  },
  {
    id: "t-098",
    side: "sell",
    status: "closed",
    volume: 0.3,
    entry_price: 2360.4,
    stop_loss: 2368.0,
    exit_price: 2369.1,
    pnl: -261.0,
    r_multiple: -1.0,
    reward_risk: 2.1,
    opened_at: iso(-512),
    closed_at: iso(-470),
  },
  {
    id: "t-097",
    side: "buy",
    status: "closed",
    volume: 0.4,
    entry_price: 2301.2,
    stop_loss: 2293.5,
    exit_price: 2319.4,
    pnl: 728.0,
    r_multiple: 2.36,
    reward_risk: 2.5,
    opened_at: iso(-720),
    closed_at: iso(-602),
  },
  {
    id: "t-096",
    side: "buy",
    status: "closed",
    volume: 0.3,
    entry_price: 2287.9,
    stop_loss: 2280.4,
    exit_price: 2282.1,
    pnl: -174.0,
    r_multiple: -0.77,
    reward_risk: 1.9,
    opened_at: iso(-980),
    closed_at: iso(-905),
  },
  {
    id: "t-095",
    side: "sell",
    status: "closed",
    volume: 0.4,
    entry_price: 2342.7,
    stop_loss: 2350.1,
    exit_price: 2325.3,
    pnl: 696.0,
    r_multiple: 2.35,
    reward_risk: 2.6,
    opened_at: iso(-1240),
    closed_at: iso(-1110),
  },
];

// ---------------------------------------------------------------------------
// Performance report (/performance).
// ---------------------------------------------------------------------------
export const mockPerformance: PerformanceReport = {
  window_start: iso(-60 * 24 * 90),
  window_end: iso(0),
  trades: 142,
  win_rate: 0.61,
  profit_factor: 1.92,
  expectancy_r: 0.43,
  sharpe: 1.74,
  sortino: 2.38,
  max_drawdown_pct: 0.047,
  max_drawdown_r: 6.2,
  avg_win_r: 1.86,
  avg_loss_r: -0.91,
  best_conditions: {
    trend_regime: "trending_up",
    volatility_regime: "high",
    session: "London/NY overlap",
  },
  worst_conditions: {
    trend_regime: "ranging",
    volatility_regime: "low",
    session: "Asian",
  },
  insights: [
    {
      category: "regime",
      statement:
        "Continuation longs in trending_up + high-volatility regimes win 61% with a 1.92 profit factor — the strongest cohort.",
      confidence: 0.81,
    },
    {
      category: "filter",
      statement:
        "Setups taken within 30 minutes of a high-impact news release underperform by 0.6R on average; tighten the blackout window.",
      confidence: 0.74,
    },
    {
      category: "risk",
      statement:
        "Moving to break-even at +1R reduced average loss from -1.1R to -0.91R with negligible win-rate cost.",
      confidence: 0.69,
    },
    {
      category: "selection",
      statement:
        "Ranging-regime entries account for 72% of full-stop losses; the regime quality multiplier should stay above 1.2 there.",
      confidence: 0.66,
    },
  ],
};

// ---------------------------------------------------------------------------
// Equity curve (derived, UI-only).
// ---------------------------------------------------------------------------
export const mockEquityCurve: EquityPoint[] = (() => {
  // Deterministic pseudo-random walk so SSR and CSR agree.
  const points: EquityPoint[] = [];
  let equity = 50_000;
  let r = 0;
  let seed = 7;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const start = new Date("2026-03-05T00:00:00Z").getTime();
  for (let i = 0; i < 142; i++) {
    // Positive expectancy walk: ~61% winners at +1.86R, losers at -0.91R.
    const win = rand() < 0.61;
    const tradeR = win ? 1.2 + rand() * 1.3 : -(0.6 + rand() * 0.6);
    r += tradeR;
    equity += tradeR * 250; // 0.5% risk on 50k ~ $250 per R
    points.push({
      t: new Date(start + i * 15 * 60_000 * 64).toISOString(),
      equity: Math.round(equity),
      r: Number(r.toFixed(2)),
    });
  }
  return points;
})();

// ---------------------------------------------------------------------------
// News / economic calendar (/news).
// ---------------------------------------------------------------------------
export const mockNews: NewsItem[] = [
  {
    title: "FOMC Press Conference",
    source: "Federal Reserve",
    importance: "critical",
    scheduled_at: iso(95),
    sentiment: -0.1,
    url: "https://www.federalreserve.gov/",
  },
  {
    title: "US CPI m/m (actual 0.2% vs 0.3% est)",
    source: "BLS",
    importance: "critical",
    scheduled_at: iso(-180),
    sentiment: 0.42,
    url: "https://www.bls.gov/cpi/",
  },
  {
    title: "Fed Chair Powell speaks on monetary policy",
    source: "Reuters",
    importance: "warning",
    scheduled_at: iso(300),
    sentiment: -0.05,
    url: "https://www.reuters.com/",
  },
  {
    title: "US 10-Year Note Auction",
    source: "US Treasury",
    importance: "warning",
    scheduled_at: iso(-60),
    sentiment: 0.12,
    url: "https://www.treasurydirect.gov/",
  },
  {
    title: "Gold ETF holdings rise for a third straight session",
    source: "Bloomberg",
    importance: "info",
    scheduled_at: iso(-420),
    sentiment: 0.28,
    url: "https://www.bloomberg.com/",
  },
  {
    title: "DXY slips as Treasury yields ease post-CPI",
    source: "FX Street",
    importance: "info",
    scheduled_at: iso(-150),
    sentiment: 0.34,
    url: "https://www.fxstreet.com/",
  },
  {
    title: "ECB officials signal caution on further cuts",
    source: "Financial Times",
    importance: "info",
    scheduled_at: iso(-600),
    sentiment: -0.08,
    url: "https://www.ft.com/",
  },
];
