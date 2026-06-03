import clsx from "clsx";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { DataSource } from "@/lib/api";

interface SectionProps {
  title: string;
  subtitle?: string;
  Icon?: LucideIcon;
  /** Optional content rendered on the right side of the header. */
  action?: ReactNode;
  /** When "mock", shows a subtle offline tag in the header. */
  source?: DataSource;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

/** A titled card section. Standardizes headers, padding, and the mock tag. */
export function Section({
  title,
  subtitle,
  Icon,
  action,
  source,
  className,
  bodyClassName,
  children,
}: SectionProps) {
  return (
    <section className={clsx("card", className)}>
      <div className="card-header">
        <div className="flex items-center gap-2.5">
          {Icon ? <Icon className="h-4 w-4 text-terminal-accent" aria-hidden /> : null}
          <div>
            <h2 className="card-title">{title}</h2>
            {subtitle ? <p className="card-subtitle">{subtitle}</p> : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {source === "mock" ? (
            <span className="pill text-notrade border-notrade-border bg-notrade-soft">
              mock
            </span>
          ) : null}
          {action}
        </div>
      </div>
      <div className={clsx(bodyClassName ?? "p-4")}>{children}</div>
    </section>
  );
}
