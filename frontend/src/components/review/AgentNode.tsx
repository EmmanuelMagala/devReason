import { AlertCircle, CheckCircle2, Clock3, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";
import type { AgentProgress } from "@/types";

export function AgentNode({
  agent,
  stretch = false,
}: {
  agent: AgentProgress;
  stretch?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm transition-colors",
        stretch && "flex-1",
        agent.status === "idle" && "bg-muted/60 text-muted-foreground",
        agent.status === "running" &&
          "border-blue-200 bg-blue-50 text-blue-700",
        agent.status === "done" &&
          "border-emerald-200 bg-emerald-50 text-emerald-700",
        agent.status === "error" && "border-red-200 bg-red-50 text-red-700",
      )}
    >
      {agent.status === "idle" ? <Clock3 className="h-4 w-4" /> : null}
      {agent.status === "running" ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : null}
      {agent.status === "done" ? <CheckCircle2 className="h-4 w-4" /> : null}
      {agent.status === "error" ? <AlertCircle className="h-4 w-4" /> : null}
      <span className="flex-1 font-medium">{agent.label}</span>
      {agent.findingCount !== undefined ? (
        <span className="rounded-full bg-white/80 px-2 py-0.5 text-xs font-semibold">
          {agent.findingCount}
        </span>
      ) : null}
    </div>
  );
}
