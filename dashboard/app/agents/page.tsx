"use client";

import { Bot, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { useApiResource } from "@/lib/useApi";
import { Section } from "@/components/Section";
import { AgentCard } from "@/components/AgentCard";

export default function AgentsPage() {
  const agentsRes = useApiResource(() => api.agents());
  const agents = agentsRes.data ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-terminal-text">Agents</h1>
          <p className="text-sm text-terminal-muted">
            Each agent reasons independently, scores its own confidence, and raises risk flags. The Decision Engine combines them by weight.
          </p>
        </div>
        <button
          type="button"
          onClick={agentsRes.refresh}
          className="pill text-terminal-text border-terminal-border-strong bg-terminal-surface-2 hover:text-terminal-accent"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          Refresh
        </button>
      </div>

      <Section
        title="Analytical Outputs"
        subtitle="Bias · confidence · reasoning · risk flags"
        Icon={Bot}
        source={agentsRes.source ?? undefined}
        bodyClassName="p-4"
      >
        {agents.length === 0 ? (
          <p className="text-sm text-terminal-muted">{agentsRes.loading ? "Loading agent outputs…" : "No agent outputs available."}</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {agents.map((a) => (
              <AgentCard key={a.agent} output={a} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
