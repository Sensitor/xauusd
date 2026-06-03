-- =====================================================================
-- GoldMind AI — PostgreSQL schema (authoritative DDL).
--
-- Design notes
--   * Every evaluation CYCLE writes a market_snapshot + a signal + one row
--     per agent in agent_outputs — INCLUDING no-trade cycles. The Learning
--     Engine needs the no-trades as much as the trades (selection bias kills
--     edge analysis otherwise).
--   * Money/price columns use NUMERIC (exact), never floating point.
--   * Timestamps are timestamptz (store UTC).
--   * JSONB for the flexible, agent-specific payloads so the schema is stable
--     while agents evolve; the structured, queried fields are promoted to columns.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- Market state captured at decision time
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_snapshots (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol           TEXT        NOT NULL DEFAULT 'XAUUSD',
    as_of            TIMESTAMPTZ NOT NULL,
    last_close       NUMERIC(14,4),
    h1_atr           NUMERIC(14,4),
    adx              NUMERIC(8,3),
    trend_regime     TEXT,
    phase_regime     TEXT,
    volatility_regime TEXT,
    prices           JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- {tf: close, ...}
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_snapshots_symbol_asof ON market_snapshots (symbol, as_of DESC);

-- ---------------------------------------------------------------------
-- Decision-engine verdict per cycle (BUY / SELL / NO_TRADE)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id      UUID REFERENCES market_snapshots (id) ON DELETE SET NULL,
    symbol           TEXT        NOT NULL DEFAULT 'XAUUSD',
    decision         TEXT        NOT NULL CHECK (decision IN ('BUY','SELL','NO_TRADE')),
    bias             TEXT        NOT NULL,
    confidence       NUMERIC(5,4) NOT NULL,
    quality_score    NUMERIC(6,2) NOT NULL,
    net_score        NUMERIC(6,4) NOT NULL,
    agreement        NUMERIC(5,4) NOT NULL,
    reasoning        TEXT,
    sizing           JSONB,                  -- PositionSizing snapshot (if any)
    risk_flags       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_signals_created    ON signals (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_signals_decision   ON signals (decision, created_at DESC);

-- ---------------------------------------------------------------------
-- Per-agent output per cycle (full audit trail / explainability)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_outputs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id        UUID REFERENCES signals (id) ON DELETE CASCADE,
    snapshot_id      UUID REFERENCES market_snapshots (id) ON DELETE SET NULL,
    agent            TEXT        NOT NULL,
    bias             TEXT        NOT NULL,
    confidence       NUMERIC(5,4) NOT NULL,
    reasoning        TEXT,
    risk_flags       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    analysis         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    model            TEXT,
    latency_ms       NUMERIC(10,2),
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_outputs_signal ON agent_outputs (signal_id);
CREATE INDEX IF NOT EXISTS ix_agent_outputs_agent  ON agent_outputs (agent, created_at DESC);

-- ---------------------------------------------------------------------
-- Executed trades (lifecycle: proposed -> pending -> open -> closed)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trades (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id        UUID REFERENCES signals (id) ON DELETE SET NULL,
    symbol           TEXT        NOT NULL DEFAULT 'XAUUSD',
    side             TEXT        NOT NULL CHECK (side IN ('buy','sell')),
    status           TEXT        NOT NULL DEFAULT 'proposed',
    volume           NUMERIC(10,2) NOT NULL,
    entry_price      NUMERIC(14,4),
    stop_loss        NUMERIC(14,4),
    take_profits     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    exit_price       NUMERIC(14,4),
    broker_order_id  BIGINT,
    risk_amount      NUMERIC(14,2),
    risk_pct         NUMERIC(7,5),
    reward_risk      NUMERIC(7,2),
    pnl              NUMERIC(14,2),
    r_multiple       NUMERIC(8,3),         -- realized profit in R (the learning unit)
    mae_r            NUMERIC(8,3),         -- max adverse excursion (R)
    mfe_r            NUMERIC(8,3),         -- max favorable excursion (R)
    slippage_points  NUMERIC(10,2),
    opened_at        TIMESTAMPTZ,
    closed_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_trades_status     ON trades (status);
CREATE INDEX IF NOT EXISTS ix_trades_closed_at  ON trades (closed_at DESC);

-- ---------------------------------------------------------------------
-- Chart screenshots fed to the Vision agent
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS screenshots (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id      UUID REFERENCES market_snapshots (id) ON DELETE SET NULL,
    symbol           TEXT        NOT NULL DEFAULT 'XAUUSD',
    captured_at      TIMESTAMPTZ NOT NULL,
    source           TEXT,                 -- 'tradingview', 'mt5', 'upload'
    uri              TEXT        NOT NULL,  -- path or object-store URL
    vision_output    JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Economic calendar / news
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title            TEXT        NOT NULL,
    source           TEXT,
    importance       TEXT        NOT NULL DEFAULT 'info',  -- info|warning|critical
    is_scheduled     BOOLEAN     NOT NULL DEFAULT false,
    scheduled_at     TIMESTAMPTZ,
    published_at     TIMESTAMPTZ,
    sentiment        NUMERIC(5,4),
    url              TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_news_scheduled ON news_events (scheduled_at);
CREATE INDEX IF NOT EXISTS ix_news_importance ON news_events (importance, scheduled_at);

-- ---------------------------------------------------------------------
-- Periodic performance snapshots from the Learning Engine
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS performance_metrics (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    window_start     TIMESTAMPTZ NOT NULL,
    window_end       TIMESTAMPTZ NOT NULL,
    trades           INTEGER     NOT NULL,
    win_rate         NUMERIC(5,4),
    profit_factor    NUMERIC(8,3),
    expectancy_r     NUMERIC(8,4),
    sharpe           NUMERIC(8,3),
    sortino          NUMERIC(8,3),
    max_drawdown_pct NUMERIC(7,4),
    max_drawdown_r   NUMERIC(8,3),
    avg_win_r        NUMERIC(8,3),
    avg_loss_r       NUMERIC(8,3),
    best_conditions  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    worst_conditions JSONB       NOT NULL DEFAULT '{}'::jsonb,
    insights         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Risk / circuit-breaker events (audit + alerting source)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type       TEXT        NOT NULL,  -- circuit_breaker|daily_dd|consec_losses|...
    severity         TEXT        NOT NULL DEFAULT 'warning',
    message          TEXT        NOT NULL,
    equity           NUMERIC(14,2),
    drawdown_pct     NUMERIC(7,4),
    consecutive_losses INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_risk_events_created ON risk_events (created_at DESC);

-- ---------------------------------------------------------------------
-- Convenience view: daily realized performance
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_performance AS
SELECT
    date_trunc('day', closed_at)             AS day,
    count(*)                                 AS trades,
    avg((r_multiple > 0)::int)::numeric(5,4) AS win_rate,
    sum(pnl)                                 AS pnl,
    avg(r_multiple)                          AS expectancy_r
FROM trades
WHERE status = 'closed' AND closed_at IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC;
