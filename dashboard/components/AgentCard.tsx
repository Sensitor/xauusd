import clsx from "clsx";
import {
  BarChart3,
  BookOpen,
  Bot,
  Brain,
  Cpu,
  Eye,
  Gavel,
  Globe2,
  Layers,
  Newspaper,
  Radar,
  ShieldHalf,
  Sparkles,
} from "lucide-react";
import type { AgentName, AgentOutput, Bias } from "@/lib/types";
import { fmtPct, humanize } from "@/lib/format";
import { biasClasses, biasFillClass } from "@/lib/ui";
import { RiskFlags } from "./RiskFlags";

const AGENT_ICON: Record<AgentName, typeof Bot> = {
  market_structure: Layers,
  technical: BarChart3,
  macro: Globe2,
  news_sentiment: Newspaper,
  chart_vision: Eye,
  market_regime: Radar,
  risk_manager: ShieldHalf,
  decision_engine: Gavel,
  execution: Bot,
  learning: BookOpen,
};

const AGENT_BLURB: Record<AgentName, string> = {
  market_structure: "SMC · liquidity · MTF",
  technical: "Indicators · momentum",
  macro: "DXY · yields · risk env",
  news_sentiment: "Headlines · event risk",
  chart_vision: "Patterns · S/R levels",
  market_regime: "Trend · phase · vol",
  risk_manager: "Sizing · drawdown gates",
  decision_engine: "Weighted vote · verdict",
  execution: "Routing · slippage",
  learning: "Post-trade edge mining",
};

function BiasTag({ bias }: { bias: Bias }) {
  return (
    <span className={clsx("pill", biasClasses(bias))}>
      <span className={clsx("h-1.5 w-1.5 rounded-full", biasFillClass(bias))} aria-hidden />
      {humanize(bias)}
    </span>
  );
}

interface AgentCardProps {
  output: AgentOutput;
  className?: string;
}

export function AgentCard({ output, className }: AgentCardProps) {
  const Icon = AGENT_ICON[output.agent] ?? Brain;
  const pct = Math.max(0, Math.min(1, output.confidence)) * 100;
  const flagCount = output.risk_flags?.length ?? 0;

  return (
    <article className={clsx("card flex flex-col p-4", className)}>
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-terminal-surface-2 text-terminal-accent ring-1 ring-terminal-border">
            <Icon className="h-4.5 w-4.5" aria-hidden />
          </span>
          <div>
            <h3 className="text-sm font-semibold text-terminal-text">
              {humanize(output.agent)}
            </h3>
            <p className="text-[11px] text-terminal-muted">{AGENT_BLURB[output.agent]}</p>
          </div>
        </div>
        <BiasTag bias={output.bias} />
      </header>

      <div className="mt-3.5">
        <div className="flex items-center justify-between text-[11px]">
          <span className="label">Confidence</span>
          <span className="tnum font-semibold text-terminal-text">
            {fmtPct(output.confidence, 0)}
          </span>
        </div>
        <span
          className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-terminal-surface-2"
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span
            className={clsx("block h-full rounded-full", biasFillClass(output.bias))}
            style={{ width: `${pct}%` }}
          />
        </span>
      </div>

      <p className="mt-3 flex-1 text-xs leading-relaxed text-terminal-text/85">
        {output.reasoning || "No reasoning provided."}
      </p>

      {output.model ? (
        <div className="mt-3 flex items-center gap-1.5 text-[10px] text-terminal-muted">
          <span
            className={clsx(
              "pill",
              output.model === "rule_based"
                ? "border-terminal-border bg-terminal-surface-2 text-terminal-muted"
                : "border-terminal-accent/40 bg-terminal-accent/10 text-terminal-accent",
            )}
          >
            {output.model === "rule_based" ? <Cpu className="h-3 w-3" aria-hidden /> : <Sparkles className="h-3 w-3" aria-hidden />}
            {output.model}
          </span>
          {typeof output.latency_ms === "number" ? <span className="tnum">{Math.round(output.latency_ms)} ms</span> : null}
        </div>
      ) : null}

      {flagCount > 0 ? (
        <div className="mt-3 border-t border-terminal-border pt-3">
          <RiskFlags flags={output.risk_flags} compact />
        </div>
      ) : null}
    </article>
  );
}
