import { ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState } from "@/components/shared/EmptyState";
import { FindingCard } from "@/components/review/FindingCard";
import { sortBySeverity } from "@/lib/severity";
import { cn } from "@/lib/cn";
import type { Finding } from "@/types";

type Filter = "all" | Finding["agent"];

export function FindingsList({
  findings,
  isStreaming,
}: {
  findings: Finding[];
  isStreaming: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(() => {
    const base =
      filter === "all"
        ? findings
        : findings.filter((finding) => finding.agent === filter);
    return sortBySeverity(base);
  }, [filter, findings]);

  if (!findings.length && !isStreaming) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No findings yet"
        description="Findings appear here when the merged review payload arrives from the backend."
      />
    );
  }

  const counts = {
    all: findings.length,
    code_analyst: findings.filter((finding) => finding.agent === "code_analyst")
      .length,
    security_agent: findings.filter(
      (finding) => finding.agent === "security_agent",
    ).length,
    semantic_security_agent: findings.filter(
      (finding) => finding.agent === "semantic_security_agent",
    ).length,
    architecture_agent: findings.filter(
      (finding) => finding.agent === "architecture_agent",
    ).length,
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(
          [
            "all",
            "code_analyst",
            "security_agent",
            "semantic_security_agent",
            "architecture_agent",
          ] as const
        ).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={cn(
              "rounded-xl px-3 py-2 text-left text-sm transition-colors",
              filter === value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground",
            )}
          >
            <div className="font-medium">
              {value === "all"
                ? "All"
                : value === "code_analyst"
                  ? "Code"
                  : value === "security_agent"
                    ? "Security"
                    : value === "semantic_security_agent"
                      ? "App sec"
                      : "Architecture"}
            </div>
            <div className="text-xs opacity-80">{counts[value]}</div>
          </button>
        ))}
      </div>
      <div className="space-y-3">
        {filtered.map((finding, index) => (
          <FindingCard
            key={finding.id ?? `${finding.agent}-${index}`}
            finding={finding}
            index={index}
          />
        ))}
      </div>
    </div>
  );
}
