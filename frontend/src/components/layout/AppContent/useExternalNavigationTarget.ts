import { useEffect, useState } from "react";
import {
  getExternalNavigationPreviewRequest,
  getExternalNavigationTargetFile,
  shouldScrollToBottomAfterExternalNavigation,
  type ExternalNavigationState,
} from "./externalNavigationState";

interface UseExternalNavigationTargetOptions {
  sessionId: string | null;
  locationState: ExternalNavigationState | null | undefined;
  locationKey: string;
  routeRunId: string | null;
}

export function useExternalNavigationTarget({
  sessionId,
  locationState,
  locationKey,
  routeRunId: rawRouteRunId,
}: UseExternalNavigationTargetOptions) {
  const [targetRunId, setTargetRunId] = useState<string | null>(null);
  const [targetRunPending, setTargetRunPending] = useState(false);
  const targetFile = getExternalNavigationTargetFile(locationState);
  const preview = getExternalNavigationPreviewRequest(locationState);
  const scrollToBottom =
    shouldScrollToBottomAfterExternalNavigation(locationState);
  const routeRunId = rawRouteRunId?.trim() || null;
  const token = targetFile || scrollToBottom || routeRunId ? locationKey : null;
  const targetTraceId = targetFile?.traceId ?? undefined;

  useEffect(() => {
    if (!sessionId || !targetTraceId) {
      setTargetRunId(null);
      setTargetRunPending(false);
      return;
    }

    let cancelled = false;
    setTargetRunPending(true);

    const resolveTargetRunId = async () => {
      try {
        const { sessionApi } = await import("../../../services/api");
        const response = await sessionApi.getRuns(sessionId, {
          trace_id: targetTraceId,
        });
        if (cancelled) return;

        const matchedRun =
          response.runs.find((run) => run.trace_id === targetTraceId) ?? null;
        setTargetRunId(matchedRun?.run_id ?? null);
        setTargetRunPending(false);
      } catch (err) {
        if (!cancelled) {
          console.warn(
            "[AppContent] Failed to resolve external navigation run:",
            err,
          );
          setTargetRunId(null);
          setTargetRunPending(false);
        }
      }
    };

    void resolveTargetRunId();

    return () => {
      cancelled = true;
    };
  }, [sessionId, targetTraceId]);

  return {
    externalNavigationToken: token,
    externalNavigationTargetFile: targetFile,
    externalNavigationPreview: preview,
    externalNavigationTargetRunId: targetRunId || routeRunId,
    externalNavigationTargetRunPending: targetRunPending,
    externalScrollToBottom: scrollToBottom,
  };
}
