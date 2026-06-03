# GoldMind AI — Documentation

Institutional-grade, multi-agent AI trading system for **XAUUSD (Gold)**. The
goal is not to predict price — it is to classify market conditions, filter
low-quality trades, preserve capital, and act only when multiple independent
signals align. `NO_TRADE` is the default, correct outcome.

## Read in order

1. [01 — System Architecture](./01-architecture.md) — philosophy, components, data flow, agent-communication diagram.
2. [02 — Agents](./02-agents.md) — the ten agents: responsibilities, I/O, confidence, risk flags, weighted scoring.
3. [03 — Database](./03-database.md) — PostgreSQL schema, ER diagram, design rationale.
4. [04 — LangGraph Workflow](./04-langgraph-workflow.md) — state, reducers, fan-out/fan-in, the graph.
5. [05 — API](./05-api.md) — HTTP control-plane endpoints and execution-mode gating.
6. [06 — Risk Framework](./06-risk-framework.md) — limits, sizing math, circuit breakers, prop-firm mapping.
7. [07 — Backtesting](./07-backtesting.md) — causal backtesting + walk-forward methodology.
8. [08 — Deployment](./08-deployment.md) — Docker topology, the MT5 execution node, monitoring & alerting.
9. [09 — Roadmap](./09-roadmap.md) — current status, MVP path, advanced roadmap.

## Quick orientation

- **Code**: Python package `goldmind` under `src/`. See the top-level
  [README](../README.md) for quickstart and repository layout.
- **Dashboard**: Next.js app under `dashboard/` (see its own README).
- **Run one decision now (no keys/DB needed):**
  ```bash
  pip install -r requirements.txt
  PYTHONPATH=src python -m goldmind.cli evaluate
  ```

## A note on scope

This is decision-support infrastructure, not financial advice, and the bundled
synthetic backtests validate plumbing only — never mistake them for evidence of
edge (see [07](./07-backtesting.md)).
