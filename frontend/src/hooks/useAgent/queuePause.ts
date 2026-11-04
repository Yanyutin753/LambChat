import { useCallback, useRef, useState, useMemo, type RefObject } from "react";
import i18n from "../../i18n";
import { sessionApi } from "../../services/api";

const pauseStorageKey = (sessionId: string) =>
  `lambchat:queue-pause:v1:${sessionId}`;

/** Local stop takes effect immediately; the server fence survives reconnects and API changes. */
export function useQueuePause(
  sessionIdRef: RefObject<string | null>,
  onResumeError?: (message: string) => void,
) {
  const pauses = useRef(
    new Map<
      string | null,
      { runId?: string; reason: "interrupted" | "delivery" }
    >(),
  );
  const [revision, setRevision] = useState(0);
  const [resuming, setResuming] = useState(false);
  const resumeInFlight = useRef(false);
  const setQueuePaused = useCallback(
    (
      sessionId: string | null,
      paused: boolean,
      runId?: string,
      reason: "interrupted" | "delivery" = "interrupted",
    ) => {
      if (paused) pauses.current.set(sessionId, { runId, reason });
      else pauses.current.delete(sessionId);
      if (sessionId) {
        try {
          if (paused)
            sessionStorage.setItem(
              pauseStorageKey(sessionId),
              JSON.stringify({ runId, reason }),
            );
          else sessionStorage.removeItem(pauseStorageKey(sessionId));
        } catch {
          /* The in-memory pause still prevents automatic submission. */
        }
      }
      setRevision((value) => value + 1);
    },
    [],
  );
  const isQueuePaused = useCallback((sessionId: string | null) => {
    if (sessionId && !pauses.current.has(sessionId)) {
      try {
        const saved = JSON.parse(
          sessionStorage.getItem(pauseStorageKey(sessionId)) || "null",
        );
        if (
          saved &&
          ["interrupted", "delivery"].includes(saved.reason) &&
          (saved.runId === undefined || typeof saved.runId === "string")
        )
          pauses.current.set(sessionId, saved);
      } catch {
        /* Invalid or unavailable storage is ignored. */
      }
    }
    return pauses.current.has(sessionId);
  }, []);
  const resumeQueue = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (!sessionId || resumeInFlight.current) return;
    resumeInFlight.current = true;
    setResuming(true);
    try {
      const pause = pauses.current.get(sessionId);
      const status = await sessionApi.getStatus(sessionId);
      if (pauses.current.get(sessionId) !== pause) return;
      if (!status.run_id || (pause?.runId && pause.runId !== status.run_id))
        throw new Error("Queue run changed");
      if (status.queue_paused) {
        if (!status.queue_pause_token)
          throw new Error("Queue pause token missing");
        await sessionApi.resumeQueue(
          sessionId,
          status.run_id,
          status.queue_pause_token,
        );
      }
      if (pauses.current.get(sessionId) === pause)
        setQueuePaused(sessionId, false);
    } finally {
      resumeInFlight.current = false;
      setResuming(false);
    }
  }, [sessionIdRef, setQueuePaused]);
  const onResume = useCallback(async () => {
    const owner = sessionIdRef.current;
    try {
      await resumeQueue();
    } catch {
      if (sessionIdRef.current === owner)
        onResumeError?.(i18n.t("chat.requestFailed"));
    }
  }, [resumeQueue, sessionIdRef, onResumeError]);
  const paused = isQueuePaused(sessionIdRef.current);
  const pauseReason = pauses.current.get(sessionIdRef.current)?.reason;
  const queueControl = useMemo(
    () => ({ paused, pauseReason, resuming, onResume }),
    [paused, pauseReason, resuming, onResume],
  );
  return {
    queueControl,
    queuePaused: paused,
    queuePauseReason: pauseReason,
    queueResuming: resuming,
    queuePauseRevision: revision,
    setQueuePaused,
    isQueuePaused,
    resumeQueue,
  };
}
