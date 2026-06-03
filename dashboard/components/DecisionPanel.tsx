import clsx from "clsx";
import { ArrowRight, Crosshair, Quote, Target } from "lucide-react";
import type { AgentVote, TradingDecision } from "@/lib/types";
import {
  fmtCurrency,
  fmtNumber,
  fmtPct,
  fmtPrice,
  fmtR,
  humanize,
} from "@/lib/format";
import {
  biasFillClass,
  decisionClasses,
  qualityTextClass,
  signedTextClass,
} from "@/lib/ui";
import { RiskFlags } from "./RiskFlags";

function DecisionBadge({ decision }: { decision: TradingDecision["decision"] }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-lg border px-3 py-1 text-base font-bold tracking-wide",
        decisionClasses(decision),
      )}
    >
      {decision.replace("_", " ")}
    </span>
  );
}

function MetricCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-surface-2 px-3 py-2">
      <div className="label">{label}</div>
      <div className={clsx("tnum mt-0.5 text-sm font-semibold", tone ?? "text-terminal-text")}>
        {value}
      </div>
    </div>
  );
}

function VoteRow({ vote }: { vote: AgentVote }) {
  const pct = Math.max(0, Math.min(1, vote.confidence)) * 100;
  return (
    <li className="grid grid-cols-[8.5rem_1fr_auto] items-center gap-3 py-1.5">
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-terminal-text">
          {humanize(vote.agent)}
        </div>
        <div className="text-[10px] text-terminal-muted">
          {humanize(vote.bias)} · w {fmtNumber(vote.weight, 2)}
        </div>
      </div>
      <span className="h-1.5 overflow-hidden rounded-full bg-terminal-surface-2">
        <span
          className={clsx("block h-full rounded-full", biasFillClass(vote.bias))}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span
        className={clsx("tnum w-14 text-right text-xs font-semibold", signedTextClass(vote.contribution))}
        title="Contribution = weight x signed confidence"
      >
        {vote.contribution > 0 ? "+" : ""}
        {fmtNumber(vote.contribution, 3)}
      </span>
    </li>
  );
}

interface DecisionPanelProps {
  decision: TradingDecision;
  className?: string;
}

/**
 * The decision-explanation panel: the Decision Engine's verdict, headline
 * metrics, narrative reasoning, the position-sizing ladder, the weighted votes
 * of each scoring agent, and any risk flags.
 */
export function DecisionPanel({ decision, className }: DecisionPanelProps) {
  const { sizing } = decision;

  return (
    <section className={clsx("card", className)}>
      <div className="card-header">
        <div className="flex items-center gap-3">
          <Crosshair className="h-4 w-4 text-terminal-accent" aria-hidden />
          <div>
            <h2 className="card-title">Decision Engine</h2>
            <p className="card-subtitle">
              {decision.symbol} · ID {decision.id.slice(0, 8)}
            </p>
          </div>
        </div>
        <DecisionBadge decision={decision.decision} />
      </div>

      <div className="space-y-5 p-4">
        {/* Headline metrics */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricCell
            label="Quality"
            value={`${fmtNumber(decision.quality_score, 0)}/100`}
            tone={qualityTextClass(decision.quality_score)}
          />
          <MetricCell label="Confidence" value={fmtPct(decision.confidence, 0)} />
          <MetricCell
            label="Net Score"
            value={fmtNumber(decision.net_directional_score, 2)}
            tone={signedTextClass(decision.net_directional_score)}
          />
          <MetricCell label="Agreement" value={fmtPct(decision.agreement, 0)} />
        </div>

        {/* Reasoning */}
        <div>
          <div className="label mb-1.5 flex items-center gap-1.5">
            <Quote className="h-3.5 w-3.5" aria-hidden />
            Reasoning
          </div>
          <p className="rounded-lg border border-terminal-border bg-terminal-surface-2 p-3 text-sm leading-relaxed text-terminal-text/90">
            {decision.reasoning || "No reasoning provided."}
          </p>
        </div>

        {/* Sizing ladder (only when a trade is proposed) */}
        {sizing ? (
          <div>
            <div className="label mb-1.5 flex items-center gap-1.5">
              <Target className="h-3.5 w-3.5" aria-hidden />
              Proposed Sizing
            </div>
            <div className="rounded-lg border border-terminal-border bg-terminal-surface-2 p-3">
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                <KV label="Side" value={humanize(sizing.side)} />
                <KV label="Entry" value={fmtPrice(sizing.entry)} />
                <KV label="Stop Loss" value={fmtPrice(sizing.stop_loss)} tone="text-sell" />
                <KV label="Lot Size" value={fmtNumber(sizing.lot_size, 2)} />
                <KV label="Risk" value={fmtCurrency(sizing.risk_amount)} />
                <KV label="Risk %" value={fmtPct(sizing.risk_pct, 2)} />
                <KV label="Reward:Risk" value={`${fmtNumber(sizing.reward_risk, 2)}`} tone="text-buy" />
                <KV
                  label="Break-even"
                  value={fmtPrice(sizing.break_even_price ?? undefined)}
                />
              </div>

              {sizing.take_profits.length > 0 ? (
                <div className="mt-3 border-t border-terminal-border pt-3">
                  <div className="label mb-2">Take-Profit Ladder</div>
                  <ul className="space-y-1.5">
                    {sizing.take_profits.map((tp, i) => (
                      <li
                        key={i}
                        className="flex items-center justify-between gap-3 text-xs"
                      >
                        <span className="flex items-center gap-2 text-terminal-muted">
                          <span className="grid h-5 w-5 place-items-center rounded bg-terminal-surface text-[10px] font-semibold text-terminal-text">
                            {i + 1}
                          </span>
                          TP{i + 1}
                          <ArrowRight className="h-3 w-3" aria-hidden />
                        </span>
                        <span className="tnum text-terminal-text">{fmtPrice(tp.price)}</span>
                        <span className="tnum text-buy">{fmtR(tp.r_multiple)}</span>
                        <span className="tnum text-terminal-muted">
                          close {fmtPct(tp.close_fraction, 0)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* Votes */}
        {decision.votes.length > 0 ? (
          <div>
            <div className="label mb-1.5">Agent Votes</div>
            <ul className="divide-y divide-terminal-border rounded-lg border border-terminal-border bg-terminal-surface-2 px-3 py-1">
              {decision.votes.map((v) => (
                <VoteRow key={v.agent} vote={v} />
              ))}
            </ul>
          </div>
        ) : null}

        {/* Risk flags */}
        <div>
          <div className="label mb-1.5">Risk Flags</div>
          <RiskFlags flags={decision.risk_flags} />
        </div>
      </div>
    </section>
  );
}

function KV({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={clsx("tnum text-sm font-medium", tone ?? "text-terminal-text")}>
        {value}
      </div>
    </div>
  );
}
