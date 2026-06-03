"use client";

import { AlertTriangle, CalendarClock, Newspaper } from "lucide-react";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/useApi";
import { Section } from "@/components/Section";
import { StatCard } from "@/components/StatCard";
import { NewsList } from "@/components/NewsList";

export default function NewsPage() {
  const newsRes = useApiResource(() => api.news());
  const items = newsRes.data ?? [];
  const now = Date.now();

  const highImpact = items.filter((n) => n.importance === "critical");
  const upcoming = items.filter((n) => {
    const t = n.scheduled_at ? new Date(n.scheduled_at).getTime() : NaN;
    return Number.isFinite(t) && t > now;
  });
  const upcomingHighImpact = upcoming.filter((n) => n.importance === "critical");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-terminal-text">News &amp; Event Risk</h1>
        <p className="text-sm text-terminal-muted">
          Headlines feed the sentiment read; the economic calendar drives a deterministic no-trade blackout around high-impact releases.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard label="Tracked Items" value={String(items.length)} loading={newsRes.loading} Icon={Newspaper} />
        <StatCard label="Upcoming" value={String(upcoming.length)} loading={newsRes.loading} Icon={CalendarClock} tone={upcoming.length ? "warning" : "neutral"} />
        <StatCard label="High-Impact Ahead" value={String(upcomingHighImpact.length)} loading={newsRes.loading} Icon={AlertTriangle} tone={upcomingHighImpact.length ? "negative" : "positive"} hint={`${highImpact.length} total high-impact`} />
      </div>

      <Section title="Calendar &amp; Headlines" subtitle="Sorted as provided by the feed" Icon={Newspaper} source={newsRes.source ?? undefined} bodyClassName="">
        <NewsList items={items} emptyMessage={newsRes.loading ? "Loading news…" : "No news items. Run an evaluation with a calendar feed to populate event risk."} />
      </Section>
    </div>
  );
}
