import clsx from "clsx";
import { AlertTriangle, Info, OctagonAlert } from "lucide-react";
import type { RiskFlag, Severity } from "@/lib/types";
import { humanize } from "@/lib/format";
import { severityClasses } from "@/lib/ui";

const SEVERITY_ICON: Record<Severity, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  critical: OctagonAlert,
};

/** Compact severity chip — used inline within tables and headers. */
export function SeverityChip({ severity, count }: { severity: Severity; count?: number }) {
  const Icon = SEVERITY_ICON[severity];
  return (
    <span className={clsx("pill", severityClasses(severity))}>
      <Icon className="h-3 w-3" aria-hidden />
      {humanize(severity)}
      {typeof count === "number" ? ` ${count}` : ""}
    </span>
  );
}

interface RiskFlagsProps {
  flags: RiskFlag[];
  /** When true, render condensed chips instead of full rows. */
  compact?: boolean;
  className?: string;
}

export function RiskFlags({ flags, compact = false, className }: RiskFlagsProps) {
  if (!flags || flags.length === 0) {
    return (
      <p className={clsx("text-xs text-terminal-muted", className)}>No risk flags.</p>
    );
  }

  if (compact) {
    return (
      <div className={clsx("flex flex-wrap gap-1.5", className)}>
        {flags.map((f, i) => {
          const Icon = SEVERITY_ICON[f.severity];
          return (
            <span
              key={`${f.code}-${i}`}
              className={clsx("pill", severityClasses(f.severity))}
              title={f.message}
            >
              <Icon className="h-3 w-3" aria-hidden />
              {f.code}
            </span>
          );
        })}
      </div>
    );
  }

  return (
    <ul className={clsx("space-y-2", className)} aria-label="Risk flags">
      {flags.map((f, i) => {
        const Icon = SEVERITY_ICON[f.severity];
        return (
          <li
            key={`${f.code}-${i}`}
            className={clsx(
              "flex items-start gap-2.5 rounded-lg border px-3 py-2",
              severityClasses(f.severity),
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="font-mono text-xs font-semibold">{f.code}</span>
                {f.source ? (
                  <span className="text-[11px] text-terminal-muted">
                    via {humanize(f.source)}
                  </span>
                ) : null}
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-terminal-text/90">
                {f.message}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
