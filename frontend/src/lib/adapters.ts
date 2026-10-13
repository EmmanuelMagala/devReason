import type { ArchRule, Finding, Repo, Review, StreamEvent } from "@/types";

type ApiRepo = {
  id: string;
  owner: string;
  name: string;
  created_at: string;
  github_installation_id?: number | null;
  details?: Repo["details"];
};

type ApiArchRule = {
  id: string;
  content: string;
  created_at: string;
  status: ArchRule["status"];
  source: string;
};

type ApiFinding = {
  id?: string;
  agent: Finding["agent"];
  severity: Finding["severity"];
  type: string;
  file?: string | null;
  line?: number | null;
  message: string;
  suggestion?: string | null;
  cwe_id?: string | null;
  cvss_score?: number | null;
};

type ApiReview = {
  id: string;
  pr_url: string;
  pr_number: number;
  status: Review["status"];
  created_at: string;
  completed_at?: string | null;
  findings?: ApiFinding[];
  finding_count?: number;
  report_markdown?: string | null;
  github_comment_url?: string | null;
  error_message?: string | null;
  repo_id?: string; mode?: Review["mode"]; branch?: string; commit_sha?: string; title?: string;
  scope?: Review["scope"]; coverage?: Review["coverage"]; check_outcomes?: Review["checkOutcomes"];
  recommendation?: string; posting_status?: string;
};

export function adaptRepo(repo: ApiRepo): Repo {
  return {
    id: repo.id,
    owner: repo.owner,
    name: repo.name,
    createdAt: repo.created_at,
    githubInstallationId: repo.github_installation_id ?? null,
    details: repo.details,
  };
}

export function adaptRule(rule: ApiArchRule): ArchRule {
  return {
    id: rule.id,
    content: rule.content,
    createdAt: rule.created_at,
    status: rule.status,
    source: rule.source,
  };
}

export function adaptFinding(finding: ApiFinding): Finding {
  return {
    id: finding.id,
    agent: finding.agent,
    severity: finding.severity,
    type: finding.type,
    file: finding.file,
    line: finding.line,
    message: finding.message,
    suggestion: finding.suggestion,
    cweId: finding.cwe_id,
    cvssScore: finding.cvss_score,
  };
}

export function adaptReview(review: ApiReview): Review {
  return {
    id: review.id,
    prUrl: review.pr_url,
    prNumber: review.pr_number,
    status: review.status,
    createdAt: review.created_at,
    completedAt: review.completed_at,
    findings: (review.findings ?? []).map(adaptFinding),
    findingCount: review.finding_count ?? review.findings?.length ?? 0,
    reportMarkdown: review.report_markdown,
    githubCommentUrl: review.github_comment_url,
    errorMessage: review.error_message,
    repoId: review.repo_id, mode: review.mode ?? "pr", branch: review.branch,
    commitSha: review.commit_sha, title: review.title, scope: review.scope,
    coverage: review.coverage, checkOutcomes: review.check_outcomes,
    recommendation: review.recommendation, postingStatus: review.posting_status ?? "not_requested",
  };
}

export function adaptStreamEvent(input: unknown): StreamEvent | null {
  if (!input || typeof input !== "object") {
    return null;
  }

  const value = input as {
    event?: string;
    agent?: string | null;
    data?: Record<string, unknown>;
  };
  if (!value.event || !value.data) {
    return null;
  }

  return {
    event: value.event as StreamEvent["event"],
    agent: value.agent,
    data: value.data,
  };
}

export function adaptFindingsFromStream(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.map((entry) => adaptFinding(entry as ApiFinding));
}
