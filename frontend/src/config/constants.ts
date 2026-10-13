import type { AgentName } from "@/types";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const AGENT_DISPLAY_ORDER: Array<{
  name: AgentName;
  label: string;
  parallelGroup?: 1 | 2;
}> = [
  { name: "fetch_pr", label: "Fetch PR context" },
  { name: "load_pr_history", label: "Load prior review history" },
  { name: "load_project_insights", label: "Load project insights" },
  { name: "supervisor", label: "Dispatch analysis graph" },
  { name: "code_analyst", label: "Code analysis", parallelGroup: 1 },
  { name: "security_agent", label: "Security analysis", parallelGroup: 1 },
  {
    name: "semantic_security_agent",
    label: "App security analysis",
    parallelGroup: 1,
  },
  {
    name: "architecture_agent",
    label: "Architecture analysis",
    parallelGroup: 1,
  },
  { name: "merge_findings", label: "Merge findings" },
  { name: "report_writer", label: "Write report" },
  { name: "persist_review", label: "Persist review results" },
  { name: "save_pr_memory", label: "Save PR memory" },
  {
    name: "update_project_insights",
    label: "Update project insights",
  },
  { name: "post_to_github", label: "Post to GitHub" },
  { name: "complete_review", label: "Finalize review" },
];

export const SEVERITY_ORDER = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
} as const;
