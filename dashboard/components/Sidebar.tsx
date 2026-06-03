"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  CandlestickChart,
  LayoutDashboard,
  Newspaper,
  Radar,
} from "lucide-react";

interface NavItem {
  href: string;
  label: string;
  Icon: typeof LayoutDashboard;
  description: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "Overview", Icon: LayoutDashboard, description: "Performance & latest decision" },
  { href: "/trades", label: "Trades", Icon: CandlestickChart, description: "Active & historical positions" },
  { href: "/agents", label: "Agents", Icon: Bot, description: "10-agent analytical outputs" },
  { href: "/regime", label: "Regime", Icon: Radar, description: "Market regime & behavior" },
  { href: "/news", label: "News", Icon: Newspaper, description: "Impact & upcoming events" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-terminal-border bg-terminal-surface">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-terminal-accent/15 ring-1 ring-terminal-accent/40">
          <span className="text-sm font-bold text-terminal-accent">G</span>
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-wide text-terminal-text">
            GoldMind <span className="text-terminal-accent">AI</span>
          </div>
          <div className="text-[11px] text-terminal-muted">XAUUSD · Multi-Agent</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2" aria-label="Primary">
        {NAV.map(({ href, label, Icon, description }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={clsx("nav-link", active && "nav-link-active")}
            >
              <Icon
                className={clsx(
                  "h-4.5 w-4.5 shrink-0",
                  active ? "text-terminal-accent" : "text-terminal-muted",
                )}
                aria-hidden
              />
              <span className="flex flex-col">
                <span>{label}</span>
                <span className="text-[10px] font-normal text-terminal-muted">
                  {description}
                </span>
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-terminal-border px-5 py-4">
        <p className="text-[10px] leading-relaxed text-terminal-muted">
          Institutional-grade decision support. Not financial advice. Trade
          decisions are logged and explainable.
        </p>
      </div>
    </aside>
  );
}
