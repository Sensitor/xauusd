import clsx from "clsx";
import type { LucideIcon } from "lucide-react";

export type StatTone = "neutral" | "positive" | "negative" | "warning";

const TONE_VALUE: Record<StatTone, string> = {
  neutral: "text-terminal-text",
  positive: "text-buy",
  negative: "text-sell",
  warning: "text-notrade",
};

const TONE_ICON: Record<StatTone, string> = {
  neutral: "text-terminal-muted bg-terminal-surface-2",
  positive: "text-buy bg-buy-soft",
  negative: "text-sell bg-sell-soft",
  warning: "text-notrade bg-notrade-soft",
};

interface StatCardProps {
  label: string;
  value: string;
  tone?: StatTone;
  /** Optional secondary line under the value. */
  hint?: string;
  Icon?: LucideIcon;
  /** Render a skeleton placeholder instead of content. */
  loading?: boolean;
}

export function StatCard({
  label,
  value,
  tone = "neutral",
  hint,
  Icon,
  loading = false,
}: StatCardProps) {
  if (loading) {
    return (
      <div className="card p-4" aria-busy>
        <div className="h-3 w-20 animate-pulse rounded bg-terminal-surface-2" />
        <div className="mt-3 h-7 w-24 animate-pulse rounded bg-terminal-surface-2" />
      </div>
    );
  }

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="label">{label}</span>
        {Icon ? (
          <span className={clsx("grid h-7 w-7 place-items-center rounded-lg", TONE_ICON[tone])}>
            <Icon className="h-4 w-4" aria-hidden />
          </span>
        ) : null}
      </div>
      <div className={clsx("mt-2 text-2xl font-semibold tnum", TONE_VALUE[tone])}>
        {value}
      </div>
      {hint ? <div className="mt-1 text-xs text-terminal-muted">{hint}</div> : null}
    </div>
  );
}
