"use client";

import {
  Activity,
  BarChart3,
  Gauge,
  LineChart,
  Percent,
  Sigma,
  TrendingDown,
  Trophy,
} from "lucide-react";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/useApi";
import { mockEquityCurve } from "@/lib/mock";
import { fmtNumber, fmtPct, fmtR, fmtRatio } from "@/lib/format";
import { Section } from "@/components/Section";
import { StatCard, type StatTone } from "@/components/StatCard";
import { EquityCurve } from "@/components/EquityCurve";
import { DecisionPanel } from "@/components/DecisionPanel";
import { RegimeBadge } from "@/components/RegimeBadge";
import { AgentConfidenceBars } from "@/components/AgentConfidenceBars";

function tone(value: number | null | undefined, good: number, bad: number): StatTone {
  if (typeof value !== "number" || !Number.isFinite(value)) return "neutral";
  if (value >= good) return "positive";
  if (value <= bad) return "negative";
  return "warning";
}

export default function OverviewPage() {
  const perf = useApiResource(() => api.performance());
  const evaluation = useApiResource(() => api.evaluate({ synthetic: true }));
  const p = perf.data;
  const e = evaluation.data;
  const scoringAgents = (e?.agents ?? []).filter(
    (a) => !["risk_manager", "decision_engine", "execution", "learning"].includes(a.agent),
  );

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-terminal-text">Overview</h1>
        <p className="text-sm text-terminal-muted">
          Live decision support for XAUUSD. Quality over quantity — the system stays flat unless conviction, agreement and risk all align.
        </p>
      </div>

      {/* Performance KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Win Rate" value={fmtPct(p?.win_rate)} loading={perf.loading} tone={tone(p?.win_rate, 0.5, 0.4)} Icon={Percent} />
        <StatCard label="Profit Factor" value={fmtRatio(p?.profit_factor)} loading={perf.loading} tone={tone(p?.profit_factor, 1.5, 1)} Icon={Trophy} />
        <StatCard label="Expectancy" value={fmtR(p?.expectancy_r)} loading={perf.loading} tone={tone(p?.expectancy_r, 0.01, 0)} Icon={TrendingDown} hint="per trade" />
        <StatCard label="Sharpe" value={fmtNumber(p?.sharpe ?? null, 2)} loading={perf.loading} tone={tone(p?.sharpe, 1, 0)} Icon={Sigma} hint="per trade" />
        <StatCard label="Sortino" value={fmtNumber(p?.sortino ?? null, 2)} loading={perf.loading} tone={tone(p?.sortino, 1, 0)} Icon={Activity} hint="per trade" />
        <StatCard label="Max Drawdown" value={fmtPct(p?.max_drawdown_pct)} loading={perf.loading} tone="warning" Icon={Gauge} hint={p ? `${fmtNumber(p.max_drawdown_r, 1)}R` : undefined} />
      </div>

      {/* Equity + regime */}
      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <Section title="Equity Curve" subtitle="Cumulative performance" Icon={LineChart} source={perf.source ?? undefined}>
          <EquityCurve data={mockEquityCurve} />
        </Section>
        <Section title="Market Regime" subtitle="Adaptive behavior" Icon={Gauge} source={evaluation.source ?? undefined}>
          {e ? (
            <div className="space-y-3">
              <RegimeBadge regime={e.regime} />
              <p className="text-sm leading-relaxed text-terminal-text/85">{e.regime.recommended_behavior}</p>
            </div>
          ) : (
            <p className="text-sm text-terminal-muted">Loading regime…</p>
          )}
        </Section>
      </div>

      {/* Latest decision + agent confidence */}
      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        {e ? (
          <DecisionPanel decision={e.decision} />
        ) : (
          <Section title="Decision Engine">
            <p className="text-sm text-terminal-muted">Running evaluation…</p>
          </Section>
        )}
        <Section title="Agent Confidence" subtitle="Scoring voters" Icon={BarChart3} source={evaluation.source ?? undefined}>
          <AgentConfidenceBars agents={scoringAgents} />
        </Section>
      </div>
    </div>
  );
}
