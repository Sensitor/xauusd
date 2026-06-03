import clsx from "clsx";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Gauge,
  Minus,
  Waves,
} from "lucide-react";
import type {
  MarketRegime,
  PhaseRegime,
  TrendRegime,
  VolatilityRegime,
} from "@/lib/types";
import { fmtNumber, humanize } from "@/lib/format";

function trendClasses(t: TrendRegime): string {
  if (t === "trending_up") return "text-buy border-buy-border bg-buy-soft";
  if (t === "trending_down") return "text-sell border-sell-border bg-sell-soft";
  return "text-notrade border-notrade-border bg-notrade-soft";
}

function TrendIcon({ t }: { t: TrendRegime }) {
  if (t === "trending_up") return <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />;
  if (t === "trending_down") return <ArrowDownRight className="h-3.5 w-3.5" aria-hidden />;
  return <Minus className="h-3.5 w-3.5" aria-hidden />;
}

function volatilityClasses(v: VolatilityRegime): string {
  if (v === "high") return "text-sell border-sell-border bg-sell-soft";
  if (v === "low") return "text-info border-[rgba(59,130,246,0.4)] bg-[rgba(59,130,246,0.12)]";
  return "text-terminal-muted border-terminal-border-strong bg-terminal-surface-2";
}

function phaseClasses(p: PhaseRegime): string {
  return p === "expansion"
    ? "text-notrade border-notrade-border bg-notrade-soft"
    : "text-info border-[rgba(59,130,246,0.4)] bg-[rgba(59,130,246,0.12)]";
}

/** A single regime dimension as a labelled pill. */
export function TrendBadge({ trend }: { trend: TrendRegime }) {
  return (
    <span className={clsx("pill", trendClasses(trend))}>
      <TrendIcon t={trend} />
      {humanize(trend)}
    </span>
  );
}

export function VolatilityBadge({ vol }: { vol: VolatilityRegime }) {
  return (
    <span className={clsx("pill", volatilityClasses(vol))}>
      <Waves className="h-3.5 w-3.5" aria-hidden />
      {humanize(vol)} vol
    </span>
  );
}

export function PhaseBadge({ phase }: { phase: PhaseRegime }) {
  return (
    <span className={clsx("pill", phaseClasses(phase))}>
      <Activity className="h-3.5 w-3.5" aria-hidden />
      {humanize(phase)}
    </span>
  );
}

/** Full regime summary — the three dimensions plus ADX and quality multiplier. */
export function RegimeBadge({ regime }: { regime: MarketRegime }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <TrendBadge trend={regime.trend_regime} />
      <PhaseBadge phase={regime.phase_regime} />
      <VolatilityBadge vol={regime.volatility_regime} />
      <span className="pill text-terminal-muted border-terminal-border-strong bg-terminal-surface-2 tnum">
        <Gauge className="h-3.5 w-3.5" aria-hidden />
        ADX {fmtNumber(regime.adx, 1)}
      </span>
      <span className="pill text-terminal-muted border-terminal-border-strong bg-terminal-surface-2 tnum">
        Quality x{fmtNumber(regime.quality_multiplier, 2)}
      </span>
    </div>
  );
}
