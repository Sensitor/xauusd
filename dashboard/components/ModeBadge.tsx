import clsx from "clsx";
import { ShieldCheck, UserCheck, Zap } from "lucide-react";
import type { DataSource } from "@/lib/api";
import type { ExecutionMode } from "@/lib/types";
import { humanize } from "@/lib/format";

const MODE_META: Record<
  ExecutionMode,
  { label: string; classes: string; Icon: typeof ShieldCheck }
> = {
  shadow: {
    label: "Shadow",
    classes: "text-terminal-muted border-terminal-border-strong bg-terminal-surface-2",
    Icon: ShieldCheck,
  },
  semi_auto: {
    label: "Semi-Auto",
    classes: "text-notrade border-notrade-border bg-notrade-soft",
    Icon: UserCheck,
  },
  full_auto: {
    label: "Full-Auto",
    classes: "text-buy border-buy-border bg-buy-soft",
    Icon: Zap,
  },
};

export function ModeBadge({ mode }: { mode: ExecutionMode }) {
  const meta = MODE_META[mode] ?? MODE_META.shadow;
  const { Icon } = meta;
  return (
    <span className={clsx("pill tnum", meta.classes)} title={`Execution mode: ${humanize(mode)}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {meta.label}
    </span>
  );
}

/** Small indicator showing whether data is live from the API or mocked. */
export function SourceBadge({ source }: { source: DataSource }) {
  const live = source === "api";
  return (
    <span
      className={clsx(
        "pill",
        live
          ? "text-buy border-buy-border bg-buy-soft"
          : "text-notrade border-notrade-border bg-notrade-soft",
      )}
      title={live ? "Live data from the API" : "API unreachable — showing bundled mock data"}
    >
      <span
        className={clsx(
          "h-1.5 w-1.5 rounded-full",
          live ? "bg-buy" : "bg-notrade animate-pulse-soft",
        )}
        aria-hidden
      />
      {live ? "Live" : "Offline (mock)"}
    </span>
  );
}
