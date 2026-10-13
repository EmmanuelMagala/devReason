import { cn } from "@/lib/cn";
import { severityConfig } from "@/lib/severity";
import type { Severity } from "@/types";

export function SeverityBadge({ severity }: { severity: Severity }) {
  const config = severityConfig[severity];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        config.className,
      )}
    >
      <span className={cn("h-2 w-2 rounded-full", config.dotClassName)} />
      {config.label}
    </span>
  );
}
