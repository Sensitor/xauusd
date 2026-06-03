"use client";

import { usePathname } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";
import { ModeBadge, SourceBadge } from "./ModeBadge";

const TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Overview", subtitle: "Performance & latest trading decision" },
  "/trades": { title: "Trades", subtitle: "Active positions & historical results" },
  "/agents": { title: "Agents", subtitle: "Outputs from the 10-agent ensemble" },
  "/regime": { title: "Market Regime", subtitle: "Trend, phase, volatility & recommended behavior" },
  "/news": { title: "News & Events", subtitle: "Impact analysis & upcoming high-impact events" },
};

export function Topbar() {
  const pathname = usePathname();
  const meta = TITLES[pathname] ?? { title: "GoldMind AI", subtitle: "XAUUSD multi-agent trading system" };

  // Lightweight, deduped poll for header status. Falls back to mock cleanly.
  const { data: health } = useSWR("health", () => api.health(), {
    refreshInterval: 30_000,
    revalidateOnFocus: false,
  });

  const mode = health?.data.execution_mode ?? "shadow";
  const source = health?.source ?? "mock";
  const env = health?.data.environment ?? "dev";

  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-terminal-border bg-terminal-bg/80 px-6 py-3.5 backdrop-blur">
      <div>
        <h1 className="text-base font-semibold text-terminal-text">{meta.title}</h1>
        <p className="text-xs text-terminal-muted">{meta.subtitle}</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="pill hidden text-terminal-muted border-terminal-border-strong bg-terminal-surface-2 sm:inline-flex">
          {humanize(env)}
        </span>
        <ModeBadge mode={mode} />
        <SourceBadge source={source} />
      </div>
    </header>
  );
}
