import clsx from "clsx";
import {
  CalendarClock,
  ExternalLink,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { NewsItem, Severity } from "@/lib/types";
import { fmtNumber, fmtRelative, fmtTime } from "@/lib/format";

const IMPACT_META: Record<Severity, { label: string; classes: string }> = {
  critical: { label: "High impact", classes: "text-critical border-sell-border bg-sell-soft" },
  warning: { label: "Medium impact", classes: "text-warning border-notrade-border bg-notrade-soft" },
  info: { label: "Low impact", classes: "text-info border-[rgba(59,130,246,0.4)] bg-[rgba(59,130,246,0.12)]" },
};

function SentimentTag({ value }: { value: number }) {
  const neutral = Math.abs(value) < 0.1;
  const up = value > 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span
      className={clsx(
        "tnum inline-flex items-center gap-1 text-xs font-medium",
        neutral ? "text-terminal-muted" : up ? "text-buy" : "text-sell",
      )}
      title="Headline sentiment toward gold (-1 to +1)"
    >
      {!neutral ? <Icon className="h-3.5 w-3.5" aria-hidden /> : null}
      {value > 0 ? "+" : ""}
      {fmtNumber(value, 2)}
    </span>
  );
}

interface NewsListProps {
  items: NewsItem[];
  emptyMessage?: string;
}

export function NewsList({ items, emptyMessage = "No news items." }: NewsListProps) {
  if (!items || items.length === 0) {
    return (
      <div className="grid place-items-center px-4 py-10 text-sm text-terminal-muted">
        {emptyMessage}
      </div>
    );
  }

  const now = Date.now();

  return (
    <ul className="divide-y divide-terminal-border">
      {items.map((n, i) => {
        const impact = IMPACT_META[n.importance];
        const ts = n.scheduled_at ? new Date(n.scheduled_at).getTime() : NaN;
        const upcoming = Number.isFinite(ts) && ts > now;
        return (
          <li key={`${n.title}-${i}`} className="flex items-start gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className={clsx("pill", impact.classes)}>{impact.label}</span>
                {upcoming ? (
                  <span className="pill text-terminal-text border-terminal-border-strong bg-terminal-surface-2">
                    <CalendarClock className="h-3 w-3" aria-hidden />
                    Upcoming
                  </span>
                ) : null}
                <span className="text-[11px] text-terminal-muted">{n.source}</span>
              </div>
              <p className="mt-1 text-sm font-medium leading-snug text-terminal-text">
                {n.url ? (
                  <a
                    href={n.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 hover:text-terminal-accent"
                  >
                    {n.title}
                    <ExternalLink className="h-3 w-3 opacity-60" aria-hidden />
                  </a>
                ) : (
                  n.title
                )}
              </p>
              <div className="mt-1 flex items-center gap-3 text-[11px] text-terminal-muted">
                <span className="tnum">{fmtTime(n.scheduled_at)}</span>
                <span>·</span>
                <span className={clsx("tnum", upcoming && "text-notrade")}>
                  {fmtRelative(n.scheduled_at, now)}
                </span>
              </div>
            </div>
            <div className="shrink-0 pt-0.5">
              <SentimentTag value={n.sentiment} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
