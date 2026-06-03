"use client";

import { Gauge, Radar, Sparkles, Waves } from "lucide-react";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/useApi";
import { fmtNumber, humanize } from "@/lib/format";
import { Section } from "@/components/Section";
import { StatCard } from "@/components/StatCard";
import { RegimeBadge } from "@/components/RegimeBadge";

export default function RegimePage() {
  const regimeRes = useApiResource(() => api.regime());
  const r = regimeRes.data;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-terminal-text">Market Regime</h1>
        <p className="text-sm text-terminal-muted">
          The system adapts to context instead of applying one playbook everywhere. The quality multiplier tightens the decision bar in chop.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Trend" value={r ? humanize(r.trend_regime) : "—"} loading={regimeRes.loading} Icon={Radar} tone={r?.trend_regime === "trending_up" ? "positive" : r?.trend_regime === "trending_down" ? "negative" : "warning"} />
        <StatCard label="Phase" value={r ? humanize(r.phase_regime) : "—"} loading={regimeRes.loading} Icon={Sparkles} />
        <StatCard label="Volatility" value={r ? `${humanize(r.volatility_regime)}` : "—"} loading={regimeRes.loading} Icon={Waves} tone={r?.volatility_regime === "high" ? "negative" : "neutral"} />
        <StatCard label="Quality x" value={r ? fmtNumber(r.quality_multiplier, 2) : "—"} loading={regimeRes.loading} Icon={Gauge} tone={r && r.quality_multiplier > 1 ? "warning" : "positive"} hint={r ? `ADX ${fmtNumber(r.adx, 1)}` : undefined} />
      </div>

      <Section title="Current Regime" Icon={Radar} source={regimeRes.source ?? undefined}>
        {r ? (
          <div className="space-y-4">
            <RegimeBadge regime={r} />
            <div>
              <div className="label mb-1.5">Recommended Behavior</div>
              <p className="rounded-lg border border-terminal-border bg-terminal-surface-2 p-3 text-sm leading-relaxed text-terminal-text/90">
                {r.recommended_behavior || "No behavior guidance available."}
              </p>
            </div>
            <p className="text-xs leading-relaxed text-terminal-muted">
              Trend is derived from ADX and the EMA50/200 relationship; phase from Bollinger-band width versus its history; volatility from the ATR%
              percentile. A multiplier above 1.0 means the Decision Engine demands more conviction before it will trade.
            </p>
          </div>
        ) : (
          <p className="text-sm text-terminal-muted">Loading regime…</p>
        )}
      </Section>
    </div>
  );
}
