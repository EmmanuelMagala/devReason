import { useState } from "react";
import { ChevronDown, ChevronUp, FileCode2 } from "lucide-react";
import { SeverityBadge } from "@/components/shared/SeverityBadge";
import { cn } from "@/lib/cn";
import type { Finding } from "@/types";

const agentLabels: Record<Finding["agent"], string> = {
  code_analyst: "Code analyst",
  security_agent: "Security agent",
  semantic_security_agent: "App security agent",
  architecture_agent: "Architecture agent",
};

export function FindingCard({
  finding,
  index,
  codeBase,
}: {
  finding: Finding;
  index: number;
  codeBase?: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-2xl border bg-background/70">
      <button
        type="button"
        className="flex w-full items-start gap-3 px-4 py-4 text-left"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className="font-mono text-xs text-muted-foreground">
          #{String(index + 1).padStart(2, "0")}
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <SeverityBadge severity={finding.severity} />
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              {agentLabels[finding.agent]}
            </span>
            <span className="text-xs text-muted-foreground">
              {finding.type}
            </span>
          </div>
          <p className="text-sm font-medium text-foreground">
            {finding.message}
          </p>
          {finding.file ? (
            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <FileCode2 className="h-3.5 w-3.5" />
              <span className="break-all font-mono">{finding.file}</span>
              {finding.line ? <span>line {finding.line}</span> : null}
            </div>
          ) : null}
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>
      {expanded ? (
        <div className="space-y-3 border-t px-4 py-4 text-sm text-muted-foreground">
          {codeBase && finding.file && <a className="text-primary" target="_blank" rel="noreferrer" href={`${codeBase}/${finding.file.split('/').map(encodeURIComponent).join('/')}${finding.line ? `#L${finding.line}` : ''}`}>Open code at reviewed commit ↗</a>}
          {finding.suggestion ? (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-foreground">
                Suggestion
              </div>
              <p>{finding.suggestion}</p>
            </div>
          ) : null}
          {finding.cweId || finding.cvssScore ? (
            <div className="flex flex-wrap gap-4">
              {finding.cweId ? (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-foreground">
                    CWE
                  </div>
                  <div className="font-mono">{finding.cweId}</div>
                </div>
              ) : null}
              {finding.cvssScore ? (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-foreground">
                    CVSS
                  </div>
                  <div
                    className={cn(
                      "font-mono font-semibold",
                      finding.cvssScore >= 9
                        ? "text-red-600"
                        : finding.cvssScore >= 7
                          ? "text-orange-600"
                          : "text-amber-600",
                    )}
                  >
                    {finding.cvssScore.toFixed(1)}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
