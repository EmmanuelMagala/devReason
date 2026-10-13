export type Severity = "critical" | "high" | "medium" | "low";
export type ReviewStatus = "pending" | "running" | "completed" | "partial" | "failed" | "cancelled";
export type StreamEventType =
  | "agent_start"
  | "agent_complete"
  | "tool_call"
  | "tool_result"
  | "findings_ready"
  | "token"
  | "report_token"
  | "report_ready"
  | "complete"
  | "error";

export type AgentName =
  | "fetch_pr"
  | "load_pr_history"
  | "load_project_insights"
  | "supervisor"
  | "code_analyst"
  | "security_agent"
  | "semantic_security_agent"
  | "architecture_agent"
  | "merge_findings"
  | "report_writer"
  | "persist_review"
  | "save_pr_memory"
  | "update_project_insights"
  | "post_to_github"
  | "complete_review";

export type AgentStatus = "idle" | "running" | "done" | "error";

export interface Repo {
  id: string;
  owner: string;
  name: string;
  createdAt: string;
  githubInstallationId?: number | null;
  details?: {description?: string; private?: boolean; language?: string; default_branch?: string; updated_at?: string; html_url?: string};
}

export interface GitHubAppInstallStart {
  repoId?: string | null;
}

export interface GitHubAppInstallStartResponse {
  installUrl: string;
  existingInstallationId?: number | null;
  existingInstallationManageUrl?: string | null;
}

export interface GitHubAppAccessibleRepo {
  id: number;
  owner: string;
  name: string;
  fullName: string;
}

export interface GitHubAppAccessibleReposResponse {
  installationId: number;
  repositories: GitHubAppAccessibleRepo[];
}

export interface GitHubAppInstallSync {
  installationId: number;
  state: string;
}

export interface GitHubAppInstallSyncResponse {
  installationId: number;
  repositories: Repo[];
  importedCount: number;
}

export interface GitHubAppInstallComplete {
  installationId: number;
  state: string;
  owner: string;
  name: string;
}

export interface ArchRule {
  id: string;
  content: string;
  createdAt: string;
  status: "suggested" | "approved" | "rejected";
  source: string;
}

export interface ArchRuleCreate {
  content: string;
}

export interface Finding {
  id?: string;
  agent:
    | "code_analyst"
    | "security_agent"
    | "semantic_security_agent"
    | "architecture_agent";
  severity: Severity;
  type: string;
  file?: string | null;
  line?: number | null;
  message: string;
  suggestion?: string | null;
  cweId?: string | null;
  cvssScore?: number | null;
}

export interface Review {
  id: string;
  prUrl: string;
  prNumber: number;
  status: ReviewStatus;
  createdAt: string;
  completedAt?: string | null;
  findings: Finding[];
  findingCount?: number;
  reportMarkdown?: string | null;
  githubCommentUrl?: string | null;
  errorMessage?: string | null;
  repoId?: string;
  mode: "pr" | "snapshot";
  branch?: string;
  commitSha?: string;
  title?: string;
  scope?: {offset?: number; paths?: string[]; commit_sha?: string; file_offsets?: Record<string, number>};
  coverage?: Coverage;
  checkOutcomes?: Record<string, {status: string; error?: string; warnings?: string[]}>;
  recommendation?: string;
  postingStatus: string;
}

export interface Coverage {
  total_files?: number; eligible_files?: number; reviewed_files?: number;
  reviewed_paths?: string[]; skipped_files?: number; skipped_paths?: string[];
  truncated_files?: string[]; unavailable_files?: string[]; characters?: number;
  scope_complete?: boolean; next_offset?: number | null; cache_reused?: boolean;
  reviewed_ranges?: {path: string; start: number; end: number; total: number}[];
  budget_skipped_files?: string[]; next_file_offsets?: Record<string, number>;
  unlisted_changed_files?: number;
}
export interface Page<T> {items: T[]; total: number; page: number; page_size: number}
export interface PullRequest {number: number; title: string; url: string; author: string; branch: string; draft: boolean; commit_sha: string}
export interface GitHubStatus {configured: boolean; connections: {id: string; login: string; status: string}[]}
export interface ScopePreview {commit_sha: string; paths: string[]; total_files: number; eligible_files: number; offset: number; next_offset: number | null; character_limit: number; file_limit?: number}

export interface ReviewCreate {
  prUrl?: string;
  repoId: string;
  postToGithub: boolean;
  mode?: "pr" | "snapshot";
  prNumber?: number;
  commitSha?: string;
  branch?: string;
  scope?: {offset?: number; paths?: string[]; commit_sha?: string; file_offsets?: Record<string, number>};
}

export interface AgentProgress {
  name: AgentName;
  label: string;
  status: AgentStatus;
  findingCount?: number;
}

export interface ReviewStreamState {
  reviewId: string | null;
  status: ReviewStatus | null;
  isStreaming: boolean;
  isReportStreaming: boolean;
  agents: AgentProgress[];
  findings: Finding[];
  report: string;
  githubUrl: string | null;
  error: string | null;
}

export interface StreamEvent {
  event: StreamEventType;
  agent?: string | null;
  data: Record<string, unknown>;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}
