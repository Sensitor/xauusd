# 05 — HTTP API (Control Plane)

> Part of the [GoldMind AI documentation suite](./README.md). Prev:
> [LangGraph Workflow](./04-langgraph-workflow.md) · Next:
> [Risk Framework](./06-risk-framework.md).

> **Implementation status.** The FastAPI control plane is **specified, not yet
> implemented**. The `api/` package referenced by `make run-api`
> (`uvicorn goldmind.api.main:app`) and by `pyproject` does not exist in the tree
> yet. This document is the build contract: it defines the endpoints, their
> payloads, and — importantly — the execution-mode gating they must enforce. All
> request/response shapes below are derived from the real Pydantic models in
> `src/goldmind/core/schemas.py` and the DB columns in
> `src/goldmind/db/schema.sql`, so the API can be implemented as a thin layer
> over the existing orchestrator and repository. See the
> [Roadmap](./09-roadmap.md).

The API is a *control plane*, not a trading hot path: it triggers evaluation
cycles, exposes decisions / trades / performance for the dashboard and operators,
and gates human approval in `semi_auto`. The trading loop itself runs the
[LangGraph workflow](./04-langgraph-workflow.md) on a schedule independent of HTTP.

Conventions: JSON in/out; UTC ISO-8601 timestamps; UUIDs as strings; money/price
as JSON numbers backed by `NUMERIC` columns; auth via a bearer token / API key
(operator-only) — write endpoints (`/evaluate`, `approve`) must require it.

---

## Endpoint summary

| Method | Path | Purpose | Auth |
|--------|------|---------|:----:|
| GET | `/health` | Liveness/readiness. | no |
| GET | `/config` | Effective non-secret config (weights, risk limits, mode). | yes |
| POST | `/evaluate` | Run one cycle (supports synthetic demo). | yes |
| GET | `/decisions` | Recent decisions (signals), filterable. | yes |
| GET | `/decisions/{id}` | One decision + all agent outputs. | yes |
| GET | `/trades` | Trade ledger, filterable by status. | yes |
| GET | `/trades/active` | Currently open positions. | yes |
| POST | `/trades/{id}/approve` | Approve a proposed trade (`semi_auto`). | yes |
| GET | `/performance` | Latest Learning Engine report. | yes |
| GET | `/agents` | Agent roster, weights, last outputs. | yes |
| GET | `/regime` | Latest market-regime classification. | yes |
| GET | `/news` | Upcoming calendar + blackout status. | yes |
| GET | `/metrics` | Prometheus exposition. | scrape |

---

## GET `/health`

Liveness and dependency readiness. No auth.

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "dev",
  "execution_mode": "shadow",
  "database": "connected",
  "checks": { "db": true, "llm_reasoning": true, "llm_vision": false }
}
```

`200` when healthy; `503` if a hard dependency (DB) is down.

---

## GET `/config`

The effective, **non-secret** configuration: decision weights, risk limits, model
names, symbol, timeframes, execution mode. Never returns API keys or MT5
credentials. Sourced from `goldmind.config.Settings`.

```json
{
  "environment": "dev",
  "execution_mode": "shadow",
  "symbol": "XAUUSD",
  "timeframes": ["M5", "M15", "H1", "H4"],
  "models": { "reasoning": "claude-sonnet-4-6", "vision": "gpt-4o", "fast": "claude-haiku-4-5-20251001" },
  "weights": {
    "market_structure": 0.25, "technical": 0.20, "macro": 0.20,
    "news_sentiment": 0.10, "chart_vision": 0.10, "market_regime": 0.10, "risk_manager": 0.05
  },
  "risk": {
    "max_risk_per_trade": 0.005, "max_daily_drawdown": 0.02, "max_total_drawdown": 0.06,
    "max_consecutive_losses": 3, "max_trades_per_day": 5, "max_concurrent_positions": 1,
    "min_reward_risk": 1.8, "tp_r_multiples": [1.5, 2.5, 4.0], "tp_partials": [0.5, 0.3, 0.2]
  }
}
```

---

## POST `/evaluate`

Run one evaluation cycle and (optionally) persist it. Supports a **synthetic
demo** mode so the endpoint works with zero external data — it builds a
`MarketContext` via `goldmind.backtest.synthetic.build_synthetic_context`.

**Request**

```json
{
  "synthetic": true,
  "persist": false,
  "seed": 7,
  "drift": 0.0,
  "volatility": 0.0009,
  "screenshot_path": null
}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `synthetic` | bool | `true` | If `true`, generate data; if `false`, pull live (MT5 + feeds). |
| `persist` | bool | `false` | Write snapshot/signal/agent_outputs via `persist_evaluation`. |
| `seed`,`drift`,`volatility` | num | — | Synthetic generator knobs. |
| `screenshot_path` | str\|null | `null` | Optional chart image for the Vision agent. |

**Response** — the serialized `TradingDecision` plus per-agent summaries:

```json
{
  "decision": {
    "id": "0f1c…", "symbol": "XAUUSD", "decision": "NO_TRADE", "bias": "neutral",
    "confidence": 0.34, "quality_score": 41.0, "net_directional_score": 0.12,
    "agreement": 0.50, "reasoning": "NO TRADE — no directional edge (|net| 0.12 < 0.25). …",
    "sizing": null,
    "votes": [
      {"agent": "market_structure", "bias": "bullish", "confidence": 0.41, "weight": 0.2778, "contribution": 0.114},
      {"agent": "technical", "bias": "neutral", "confidence": 0.10, "weight": 0.2222, "contribution": 0.0}
    ],
    "risk_flags": [{"code": "chop_regime", "severity": "warning", "source": "market_regime", "message": "Ranging + compression…"}]
  },
  "regime": {"trend_regime": "ranging", "phase_regime": "compression", "volatility_regime": "normal", "adx": 17.3, "quality_multiplier": 1.375},
  "risk": {"approved": false, "rejection_reason": null, "circuit_breaker_active": false},
  "persisted_signal_id": null
}
```

A BUY/SELL response additionally carries a non-null `sizing`
(`PositionSizing`: entry, stop_loss, take_profits ladder, lot_size, risk_amount,
risk_pct, reward_risk, break_even_price, trailing_distance).

> `/evaluate` **never places an order**, regardless of mode — it computes a
> decision. Routing happens in the trading loop / via `approve`. This separation
> is what makes the endpoint safe to call freely.

---

## GET `/decisions`

Recent signals, newest first (backed by `ix_signals_created` /
`ix_signals_decision`).

Query params: `limit` (default 50), `decision` (`BUY|SELL|NO_TRADE`),
`since` (ISO timestamp), `min_quality`.

```json
{
  "items": [
    {"id": "…", "created_at": "2026-06-03T13:05:00Z", "decision": "SELL", "bias": "bearish",
     "quality_score": 68.0, "net_score": -0.41, "agreement": 0.72, "confidence": 0.57}
  ],
  "count": 1
}
```

## GET `/decisions/{id}`

One decision with its **full agent trail** — the explainability view, joining
`signals` → `agent_outputs`. Returns the signal plus an `agent_outputs[]` array
(each: agent, bias, confidence, reasoning, risk_flags, analysis, model,
latency_ms, error) and the linked `snapshot`. `404` if unknown.

---

## GET `/trades` and `/trades/active`

`/trades` — the ledger from the `trades` table. Params: `status`
(`proposed|pending|open|closed`), `limit`, `since`. Each item mirrors the trade
row: side, status, volume, entry/stop/exit, `take_profits`, `pnl`, `r_multiple`,
`mae_r`, `mfe_r`, `slippage_points`, timestamps.

`/trades/active` — convenience filter for `status = 'open'` (uses
`ix_trades_status`), the set the Execution Engine manages.

```json
{
  "items": [
    {"id": "…", "side": "buy", "status": "open", "volume": 0.27, "entry_price": 2351.40,
     "stop_loss": 2347.85, "take_profits": [{"price":2356.7,"r_multiple":1.5,"close_fraction":0.5}],
     "r_multiple": null, "opened_at": "2026-06-03T12:40:00Z"}
  ],
  "count": 1
}
```

---

## POST `/trades/{id}/approve` — execution-mode gating

The human-in-the-loop gate. Its behavior is **defined by
`settings.execution_mode`** and mirrors `ExecutionEngine.execute(..., approved=)`:

| Mode | Behavior of `approve` |
|------|-----------------------|
| `shadow` | **Rejected** (`409`). Shadow never routes orders; approval is meaningless. |
| `semi_auto` | **The intended path.** Marks the proposed trade approved and routes it through the broker; returns the `OrderResult`. |
| `full_auto` | **No-op / `409`.** `full_auto` routes automatically without waiting for approval; manual approval is redundant. |

**Request**

```json
{ "approved": true, "note": "operator-confirmed; structure + macro aligned" }
```

**Response (`semi_auto`, accepted)**

```json
{
  "trade_id": "…", "routed": true,
  "order_result": {"accepted": true, "broker_order_id": 100231, "filled_price": 2351.42,
                   "requested_price": 2351.40, "slippage_points": 0.02, "latency_ms": 38.0, "retcode": 10009}
}
```

Errors: `404` unknown trade; `409` trade not in `proposed` status, or mode does
not permit manual approval; `502` broker rejected (carries the broker `retcode`
and message). Approval must be **idempotent** — a second approve of an
already-routed trade returns the original result, never a duplicate order.

---

## GET `/performance`

The latest `PerformanceReport` from the Learning Engine (from
`performance_metrics`, or computed on demand from `fetch_closed_trades`).

```json
{
  "window_start": "2026-05-01T00:00:00Z", "window_end": "2026-06-03T00:00:00Z",
  "trades": 42, "win_rate": 0.452, "profit_factor": 1.58, "expectancy_r": 0.21,
  "sharpe": 0.34, "sortino": 0.51, "max_drawdown_r": 4.8, "avg_win_r": 2.1, "avg_loss_r": -0.95,
  "best_conditions": {"regime:trending_up": {"n": 11, "expectancy_r": 0.62}},
  "worst_conditions": {"agreement:low_agree": {"n": 14, "expectancy_r": -0.18}},
  "insights": [
    {"category": "selection", "confidence": 0.65,
     "statement": "High-agreement trades materially outperform low-agreement ones. Raise min_agreement.",
     "evidence": {"low_agree_exp": -0.18, "high_agree_exp": 0.39}}
  ]
}
```

---

## GET `/agents`, `/regime`, `/news`

- **`/agents`** — the roster: each agent's `AgentName`, decision weight,
  deterministic-vs-LLM nature, and (optionally) its most recent output. Useful
  for a dashboard "agent board".
- **`/regime`** — the latest `MarketRegimeOutput`: trend / phase / volatility
  regime, ADX, `quality_multiplier`, and `recommended_behavior`.
- **`/news`** — upcoming calendar events with importance plus the current
  blackout status (`in_blackout_window`, `minutes_to_next_high_impact`) from the
  News agent's deterministic gate.

```json
// GET /news
{
  "in_blackout_window": false,
  "minutes_to_next_high_impact": 184.0,
  "events": [
    {"title": "US CPI m/m", "importance": "critical", "scheduled_at": "2026-06-03T12:30:00Z", "is_scheduled": true}
  ]
}
```

---

## GET `/metrics`

Prometheus exposition (text format) for the scraper. Recommended series: cycle
latency histogram, per-agent latency, decisions by type, current
drawdown/equity, circuit-breaker state, open positions, LLM error rate. Wired to
Grafana in [Deployment](./08-deployment.md).

---

## Error model

A consistent JSON error envelope, mapping the domain exceptions
(`core/exceptions.py`):

```json
{ "error": { "type": "RiskRejection", "rule": "min_reward_risk", "message": "Blended RR 1.62 < minimum 1.80." } }
```

| Exception | HTTP | When |
|-----------|:----:|------|
| `DataUnavailableError` | 424 | A required feed (candles/news/macro) is missing. |
| `RiskRejection` | 409 | A hard risk rule blocked the action (normal control flow). |
| `BrokerConnectionError` | 502 | MT5 terminal/broker unreachable. |
| `ExecutionError` | 502 | Order placement/modification/close failed (carries `retcode`). |
| `ConfigError` | 500 | Invalid configuration at startup. |
| (validation) | 422 | Pydantic request-body validation failure. |

Next: [Risk Framework](./06-risk-framework.md).
