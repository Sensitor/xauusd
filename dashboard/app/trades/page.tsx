"use client";

import { Activity, CandlestickChart, History, Layers } from "lucide-react";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/useApi";
import { fmtCurrency, fmtNumber, fmtR } from "@/lib/format";
import { Section } from "@/components/Section";
import { StatCard, type StatTone } from "@/components/StatCard";
import { TradesTable } from "@/components/TradesTable";

export default function TradesPage() {
  const all = useApiResource(() => api.trades());
  const trades = all.data ?? [];
  const active = trades.filter((t) => t.status === "open" || t.status === "pending");
  const closed = trades.filter((t) => t.status === "closed");

  const realized = closed.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
  const totalR = closed.reduce((sum, t) => sum + (t.r_multiple ?? 0), 0);
  const wins = closed.filter((t) => (t.r_multiple ?? 0) > 0).length;
  const winRate = closed.length ? wins / closed.length : null;
  const realizedTone: StatTone = realized > 0 ? "positive" : realized < 0 ? "negative" : "neutral";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-terminal-text">Trades</h1>
        <p className="text-sm text-terminal-muted">Active positions and historical, fully-explained executions.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Open Positions" value={String(active.length)} loading={all.loading} Icon={Activity} tone={active.length ? "warning" : "neutral"} />
        <StatCard label="Closed Trades" value={String(closed.length)} loading={all.loading} Icon={History} />
        <StatCard label="Realized PnL" value={fmtCurrency(realized, { signed: true })} loading={all.loading} tone={realizedTone} hint={`${fmtR(totalR)} total`} />
        <StatCard label="Win Rate" value={winRate === null ? "—" : `${fmtNumber(winRate * 100, 0)}%`} loading={all.loading} tone={winRate && winRate >= 0.5 ? "positive" : "warning"} />
      </div>

      <Section title="Active Positions" subtitle={`${active.length} open`} Icon={CandlestickChart} source={all.source ?? undefined} bodyClassName="">
        <TradesTable trades={active} showClose={false} emptyMessage="No open positions — the system is flat." />
      </Section>

      <Section title="Trade History" subtitle={`${closed.length} closed`} Icon={Layers} source={all.source ?? undefined} bodyClassName="">
        <TradesTable trades={closed} emptyMessage="No closed trades yet." />
      </Section>
    </div>
  );
}
