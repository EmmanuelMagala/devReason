import { create } from "zustand";
import { AGENT_DISPLAY_ORDER } from "@/config/constants";
import type {
  AgentName,
  AgentProgress,
  AgentStatus,
  Finding,
  Review,
  ReviewStatus,
} from "@/types";

const parallelGroupByAgent = new Map(
  AGENT_DISPLAY_ORDER.map((agent) => [agent.name, agent.parallelGroup]),
);
const orderedAgentNames = AGENT_DISPLAY_ORDER.map((agent) => agent.name);

function buildAgents(): AgentProgress[] {
  return AGENT_DISPLAY_ORDER.map((agent) => ({
    name: agent.name,
    label: agent.label,
    status: "idle",
  }));
}

function markProgression(agents: AgentProgress[], currentAgent: AgentName) {
  const currentIndex = orderedAgentNames.indexOf(currentAgent);
  const currentGroup = parallelGroupByAgent.get(currentAgent);

  return agents.map((agent, index) => {
    if (agent.name === currentAgent) {
      return { ...agent, status: "running" as AgentStatus };
    }

    const sameGroup =
      currentGroup !== undefined &&
      parallelGroupByAgent.get(agent.name) === currentGroup;
    if (index < currentIndex && agent.status === "running" && !sameGroup) {
      return { ...agent, status: "done" as AgentStatus };
    }

    return agent;
  });
}

function isRunningStatus(status: ReviewStatus | null) {
  return status === "pending" || status === "running";
}

function isTerminalStatus(status: ReviewStatus | null) {
  return status === "completed" || status === "failed";
}

type ReviewStoreState = {
  reviewId: string | null;
  status: ReviewStatus | null;
  isStreaming: boolean;
  isReportStreaming: boolean;
  agents: AgentProgress[];
  findings: Finding[];
  report: string;
  githubUrl: string | null;
  error: string | null;
  startReview: (reviewId: string) => void;
  loadReview: (review: Review) => void;
  startAgent: (agentName: AgentName) => void;
  completeAgent: (agentName: AgentName, findingCount?: number) => void;
  setFindings: (findings: Finding[]) => void;
  appendReportToken: (token: string) => void;
  setReportReady: (report: string) => void;
  completeReview: (githubUrl?: string | null, report?: string | null) => void;
  failReview: (message: string) => void;
  reset: () => void;
};

const initialState = {
  reviewId: null,
  status: null,
  isStreaming: false,
  isReportStreaming: false,
  agents: buildAgents(),
  findings: [],
  report: "",
  githubUrl: null,
  error: null,
} satisfies Omit<
  ReviewStoreState,
  | "startReview"
  | "loadReview"
  | "startAgent"
  | "completeAgent"
  | "setFindings"
  | "appendReportToken"
  | "setReportReady"
  | "completeReview"
  | "failReview"
  | "reset"
>;

export const useReviewStore = create<ReviewStoreState>((set) => ({
  ...initialState,
  startReview: (reviewId) =>
    set({
      ...initialState,
      reviewId,
      status: "pending",
      isStreaming: true,
    }),
  loadReview: (review) =>
    set((state) => {
      const isSameReview = state.reviewId === review.id;
      if (!isSameReview) state = { ...state, ...initialState };
      const keepLocalTerminalStatus =
        isSameReview &&
        isTerminalStatus(state.status) &&
        isRunningStatus(review.status);
      const nextStatus = keepLocalTerminalStatus ? state.status : review.status;
      const keepLiveFindings =
        isSameReview &&
        state.isStreaming &&
        state.findings.length > 0 &&
        review.findings.length === 0;
      const keepLiveReport =
        isSameReview &&
        state.isReportStreaming &&
        !review.reportMarkdown &&
        Boolean(state.report);
      const keepLiveGithubUrl =
        isSameReview && Boolean(state.githubUrl) && !review.githubCommentUrl;

      return {
        reviewId: review.id,
        status: nextStatus,
        isStreaming: isRunningStatus(nextStatus),
        isReportStreaming:
          state.isReportStreaming && isRunningStatus(nextStatus),
        agents: isTerminalStatus(nextStatus)
          ? state.agents.map((agent) => ({
              ...agent,
              status: agent.status === "running" ? "done" : agent.status,
            }))
          : state.agents,
        findings: keepLiveFindings ? state.findings : review.findings,
        report: keepLiveReport
          ? state.report
          : (review.reportMarkdown ?? state.report),
        githubUrl: keepLiveGithubUrl
          ? state.githubUrl
          : (review.githubCommentUrl ?? state.githubUrl),
        error: review.errorMessage ?? state.error,
      };
    }),
  startAgent: (agentName) =>
    set((state) => ({
      status: "running",
      isStreaming: true,
      agents: markProgression(state.agents, agentName),
    })),
  completeAgent: (agentName, findingCount) =>
    set((state) => ({
      agents: state.agents.map((agent) =>
        agent.name === agentName
          ? {
              ...agent,
              status: "done" as AgentStatus,
              ...(findingCount !== undefined ? { findingCount } : {}),
            }
          : agent,
      ),
    })),
  setFindings: (findings) => set({ findings }),
  appendReportToken: (token) =>
    set((state) => ({
      report: `${state.report}${token}`,
      isReportStreaming: true,
      isStreaming: true,
      status: "running",
    })),
  setReportReady: (report) =>
    set(() => ({
      report,
      isReportStreaming: false,
      isStreaming: true,
      status: "running",
    })),
  completeReview: (githubUrl, report) =>
    set((state) => ({
      status: "completed",
      isStreaming: false,
      isReportStreaming: false,
      agents: state.agents.map((agent) => ({
        ...agent,
        status: agent.status === "idle" ? "idle" : "done",
      })),
      githubUrl: githubUrl ?? state.githubUrl,
      report: report ?? state.report,
    })),
  failReview: (message) =>
    set((state) => ({
      status: "failed",
      isStreaming: false,
      isReportStreaming: false,
      agents: state.agents.map((agent) =>
        agent.status === "running"
          ? { ...agent, status: "error" as AgentStatus }
          : agent,
      ),
      error: message,
    })),
  reset: () => set(initialState),
}));
