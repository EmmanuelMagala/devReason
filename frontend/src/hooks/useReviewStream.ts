import { startTransition, useEffect, useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { reviewsApi } from "@/api/reviews";
import { adaptFindingsFromStream, adaptStreamEvent } from "@/lib/adapters";
import { getClerkToken } from "@/lib/clerk";
import { useReviewStore } from "@/stores/reviewStore";
import type { AgentName } from "@/types";

export function useReviewStream(reviewId: string | null) {
  const controllerRef = useRef<AbortController | null>(null);
  const pendingReportChunkRef = useRef("");
  const reportFlushTimerRef = useRef<number | null>(null);
  const startAgent = useReviewStore((state) => state.startAgent);
  const completeAgent = useReviewStore((state) => state.completeAgent);
  const setFindings = useReviewStore((state) => state.setFindings);
  const appendReportToken = useReviewStore((state) => state.appendReportToken);
  const setReportReady = useReviewStore((state) => state.setReportReady);
  const completeReview = useReviewStore((state) => state.completeReview);
  const failReview = useReviewStore((state) => state.failReview);

  useEffect(() => {
    if (!reviewId) {
      return undefined;
    }

    const controller = new AbortController();
    controllerRef.current?.abort();
    controllerRef.current = controller;

    const flushPendingReportChunk = () => {
      if (reportFlushTimerRef.current !== null) {
        window.clearTimeout(reportFlushTimerRef.current);
        reportFlushTimerRef.current = null;
      }

      if (!pendingReportChunkRef.current) {
        return;
      }

      const chunk = pendingReportChunkRef.current;
      pendingReportChunkRef.current = "";
      startTransition(() => {
        appendReportToken(chunk);
      });
    };

    const scheduleReportChunkFlush = () => {
      if (reportFlushTimerRef.current !== null) {
        return;
      }

      reportFlushTimerRef.current = window.setTimeout(() => {
        reportFlushTimerRef.current = null;
        flushPendingReportChunk();
      }, 120);
    };

    void (async () => {
      const token = await getClerkToken();

      await fetchEventSource(reviewsApi.streamUrl(reviewId), {
        signal: controller.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        openWhenHidden: true,
        onmessage(message) {
          if (!message.data || message.data === ": keepalive") {
            return;
          }

          let parsed: unknown;
          try {
            parsed = JSON.parse(message.data);
          } catch {
            return;
          }

          const event = adaptStreamEvent(parsed);
          if (!event) {
            return;
          }

          switch (event.event) {
            case "agent_start":
              if (event.agent) {
                startAgent(event.agent as AgentName);
              }
              break;
            case "agent_complete":
              if (event.agent) {
                completeAgent(
                  event.agent as AgentName,
                  Number(event.data.count ?? 0),
                );
              }
              break;
            case "findings_ready":
              setFindings(adaptFindingsFromStream(event.data.findings));
              break;
            case "report_token":
              if (typeof event.data.token === "string") {
                pendingReportChunkRef.current += event.data.token;
                scheduleReportChunkFlush();
              }
              break;
            case "report_ready":
              if (typeof event.data.report === "string") {
                pendingReportChunkRef.current = "";
                if (reportFlushTimerRef.current !== null) {
                  window.clearTimeout(reportFlushTimerRef.current);
                  reportFlushTimerRef.current = null;
                }
                setReportReady(event.data.report);
              }
              break;
            case "complete":
              flushPendingReportChunk();
              completeReview(
                typeof event.data.github_url === "string"
                  ? event.data.github_url
                  : null,
                typeof event.data.report === "string"
                  ? event.data.report
                  : null,
              );
              controller.abort();
              break;
            case "error":
              pendingReportChunkRef.current = "";
              if (reportFlushTimerRef.current !== null) {
                window.clearTimeout(reportFlushTimerRef.current);
                reportFlushTimerRef.current = null;
              }
              failReview(
                typeof event.data.message === "string"
                  ? event.data.message
                  : "Review stream failed",
              );
              controller.abort();
              break;
            default:
              break;
          }
        },
        onerror(error) {
          if (error instanceof Error && error.name === "AbortError") {
            return;
          }

          failReview("Connection to the review stream was lost");
          throw error;
        },
      });
    })().catch(() => {
      if (!controller.signal.aborted) {
        failReview("Unable to open the review stream");
      }
    });

    return () => {
      pendingReportChunkRef.current = "";
      if (reportFlushTimerRef.current !== null) {
        window.clearTimeout(reportFlushTimerRef.current);
        reportFlushTimerRef.current = null;
      }
      controller.abort();
    };
  }, [
    completeAgent,
    completeReview,
    failReview,
    reviewId,
    setFindings,
    setReportReady,
    startAgent,
    appendReportToken,
  ]);
}
