import clsx from "clsx";
import type { AgentOutput } from "@/lib/types";
import { fmtPct, humanize } from "@/lib/format";
import { biasFillClass, biasTextClass } from "@/lib/ui";

interface AgentConfidenceBarsProps {
  agents: AgentOutput[];
  className?: string;
}

/**
 * Per-agent confidence bars, colored by directional bias
 * (green = bullish, red = bearish, amber = neutral).
 */
export function AgentConfidenceBars({ agents, className }: AgentConfidenceBarsProps) {
  if (!agents || agents.length === 0) {
    return <p className="text-xs text-terminal-muted">No agent outputs available.</p>;
  }

  return (
    <ul className={clsx("space-y-2.5", className)}>
      {agents.map((a) => {
        const pct = Math.max(0, Math.min(1, a.confidence)) * 100;
        return (
          <li key={a.agent} className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-3">
            <span className="truncate text-xs font-medium text-terminal-text" title={humanize(a.agent)}>
              {humanize(a.agent)}
            </span>
            <span
              className="h-2 overflow-hidden rounded-full bg-terminal-surface-2"
              role="progressbar"
              aria-valuenow={Math.round(pct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${humanize(a.agent)} confidence`}
            >
              <span
                className={clsx("block h-full rounded-full transition-all", biasFillClass(a.bias))}
                style={{ width: `${pct}%` }}
              />
            </span>
            <span className={clsx("tnum text-right text-xs font-semibold", biasTextClass(a.bias))}>
              {fmtPct(a.confidence, 0)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
