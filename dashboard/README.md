# GoldMind AI — Dashboard

A Next.js 14 (App Router) + TypeScript + Tailwind "trading terminal" for the
GoldMind XAUUSD multi-agent system. It visualizes performance, trades, the ten
agent outputs, market regime, and event risk.

## Pages

| Route      | Shows |
|------------|-------|
| `/`        | Performance KPIs (win rate, profit factor, expectancy, Sharpe, Sortino, max DD), equity curve, latest decision + reasoning, agent confidence |
| `/trades`  | Active positions, full trade history, realized PnL/R |
| `/agents`  | All ten agent cards — bias, confidence, reasoning, risk flags |
| `/regime`  | Trend / phase / volatility regime, ADX, quality multiplier, recommended behavior |
| `/news`    | Economic calendar + headlines, impact, sentiment, upcoming high-impact events |

## Run

```bash
cd dashboard
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_BASE if not localhost:8000
npm run dev                        # http://localhost:3000
```

Point it at the backend:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Offline / mock mode

The data layer (`lib/api.ts`) is resilient: every endpoint has a typed mock
fallback (`lib/mock.ts`). If the FastAPI backend is unreachable, the UI renders
realistic mock data and tags affected panels with a small **mock** badge — so the
dashboard is fully demoable with no backend running.

## Structure

```
app/            App Router pages (one per route) + layout + globals.css
components/     Presentational components (StatCard, DecisionPanel, AgentCard,
                TradesTable, EquityCurve, RegimeBadge, NewsList, RiskFlags, …)
lib/
  types.ts      TypeScript mirror of the backend contract (goldmind.core.schemas)
  api.ts        Resilient fetch client (api + mock fallback)
  mock.ts       Realistic mock payloads
  useApi.ts     Tiny data hook over the api client
  format.ts     Null-safe number/price/%/R/time formatters
  ui.ts         Domain → Tailwind color tokens (BUY/SELL/NO_TRADE, severity)
```

## Notes

- Colors: BUY = green, SELL = red, NO_TRADE/neutral = amber; severity follows
  the same language for risk flags.
- The equity curve series is currently a UI-only mock; wire it to a future
  `/equity` or `/backtest` endpoint when historical equity is persisted.
- This is decision-support tooling, not financial advice.
