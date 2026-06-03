# 09 — Development Roadmap

> Part of the [GoldMind AI documentation suite](./README.md). See also:
> [Architecture](./01-architecture.md) ·
> [Agents](./02-agents.md) ·
> [Database](./03-database.md) ·
> [LangGraph Workflow](./04-langgraph-workflow.md) ·
> [API](./05-api.md) ·
> [Risk Framework](./06-risk-framework.md) ·
> [Backtesting](./07-backtesting.md) ·
> [Deployment](./08-deployment.md)

---

## Current status (v0.1 — foundation)

Implemented and tested:

- ✅ Ten agents: 6 deterministic/LLM analytical voters, deterministic Risk Manager,
  Decision Engine, Execution Engine (broker-agnostic + PaperBroker), Learning Engine.
- ✅ LangGraph orchestration (parallel fan-out → risk → decision) **and** an
  equivalent direct `Orchestrator`; both validated to agree.
- ✅ Causal technical indicators, SMC structure detection, regime classification.
- ✅ Fixed-fractional risk sizing + circuit breakers + trade management.
- ✅ Backtesting engine (pessimistic fills, live risk gates) + walk-forward harness.
- ✅ PostgreSQL schema + SQLAlchemy models + persistence repository.
- ✅ FastAPI control plane (graceful DB-less degradation) + Prometheus metrics + CLI.
- ✅ Next.js dashboard (performance / trades / agents / regime / news) with offline mock.
- ✅ Docker Compose stack, Grafana provisioning, 50+ unit/integration tests, lint clean.

Not yet done (by design — these need real data/keys/capital):

- ⛔ Live market-data ingestion wired end-to-end (MT5 worker loop, news/macro feeds).
- ⛔ Real historical backtests on years of XAUUSD ticks.
- ⛔ Calibrated confidence (agents currently self-report; not yet probability-calibrated).
- ⛔ Closed-loop learning (insights are produced but not auto-applied to config).

## MVP roadmap (to first supervised live trading)

| # | Milestone | Outcome |
|---|-----------|---------|
| M1 | **Data ingestion** | MT5 worker streams M5–H4 + account state into `MarketContext`; ForexFactory calendar + a news feed populate `ctx.raw`. |
| M2 | **Persistence loop** | Every cycle (trade + no-trade) written to `signals`/`agent_outputs`/`market_snapshots`; trades tracked through their lifecycle. |
| M3 | **Real backtests** | Ingest ≥3 years of XAUUSD M5; walk-forward with CPCV; report net-of-cost OOS expectancy + drawdown distribution. |
| M4 | **Shadow mode in prod** | Run live in `shadow` for ≥1 month; compare logged decisions to what actually happened; tune thresholds. |
| M5 | **Semi-auto** | Human approves each proposal via the dashboard (`/trades/{id}/approve`); execution worker routes + manages. |
| M6 | **Alerting** | Grafana alerts on drawdown, breaker trips, feed/worker liveness, LLM latency. |

Exit criterion for the MVP: positive, stable OOS expectancy net of costs across
multiple walk-forward folds, and a clean month of shadow-mode decisions whose
rationale holds up under review.

## Advanced roadmap

| Theme | Direction |
|-------|-----------|
| **Confidence calibration** | Fit isotonic/Platt calibration on historical agent confidence vs. realized outcome so weights reflect *calibrated* probabilities, not self-reports. |
| **Closed-loop learning** | Let the Learning Engine propose config deltas (tighten `min_quality` in negative-expectancy regimes, widen news blackout) behind a human-approved change gate. |
| **Adaptive sizing** | Capped fractional-Kelly scaled by measured per-regime edge; volatility targeting for smoother equity. |
| **Vision & news depth** | Fine-tune / few-shot the Vision agent on labeled XAUUSD charts; entity-level news impact modeling instead of headline sentiment. |
| **Regime model** | Replace threshold rules with an HMM / clustering regime model; let regime drive both behavior and agent weights. |
| **RL overlay** | A constrained RL policy for trade management (BE/trailing/partial timing) trained in the backtester, bounded by the same hard risk gates. |
| **Multi-instrument** | Add silver / DXY / related instruments with correlation-aware sizing; gold stays the primary. |
| **Execution quality** | Smart order routing, slippage modeling around news, multi-broker failover. |
| **Governance** | Full audit export, model/version pinning per decision, reproducible replay of any historical cycle. |

## Guiding constraints (do not regress)

Every item above must preserve the three invariants from
[Architecture §1](./01-architecture.md): **capital preservation dominates,
explainability is non-negotiable, determinism where it matters.** New ML/LLM
capability is welcome only in roles where a wrong-but-plausible answer degrades
*quality*, never *safety* — the deterministic risk gate stays in front of
execution no matter how sophisticated the analysis becomes.
