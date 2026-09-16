import { useCallback, useRef, useState } from "react";
import type { SteerItem } from "../../utils/mergeSteers";

const storageKey = (sessionId: string) =>
  `lambchat:queued-follow-ups:v1:${sessionId}`;

function readQueue(sessionId: string | null): SteerItem[] {
  if (!sessionId) return [];
  try {
    const value: unknown = JSON.parse(
      sessionStorage.getItem(storageKey(sessionId)) || "[]",
    );
    if (!Array.isArray(value)) return [];
    return value.flatMap((item) => {
      if (
        !item ||
        typeof item.id !== "string" ||
        typeof item.content !== "string" ||
        item.status !== "deferred" ||
        typeof item.timestamp !== "string"
      )
        return [];
      const timestamp = new Date(item.timestamp);
      if (!Number.isFinite(timestamp.getTime())) return [];
      if (
        item.attachments !== undefined &&
        (!Array.isArray(item.attachments) ||
          !item.attachments.every(
            (file: Record<string, unknown> | null) =>
              file &&
              ["id", "key", "name", "mimeType"].every(
                (key) => typeof file[key] === "string",
              ) &&
              typeof file.size === "number" &&
              file.size > 0,
          ))
      )
        return [];
      return [
        { ...item, timestamp, queued: true, deferred: true } as SteerItem,
      ];
    });
  } catch {
    return [];
  }
}

function saveQueue(sessionId: string | null, items: SteerItem[]) {
  if (!sessionId) return;
  try {
    // Backend steers already have server persistence. Keeping local copies
    // would resurrect messages delivered while this tab was disconnected.
    const queued = items.filter((item) => item.status === "deferred");
    if (queued.length)
      sessionStorage.setItem(storageKey(sessionId), JSON.stringify(queued));
    else sessionStorage.removeItem(storageKey(sessionId));
  } catch (error) {
    console.warn("Unable to persist queued follow-ups", error);
  }
}

/** Tab-scoped persistence survives reloads without auto-sending one queue in multiple tabs. */
export function useQueuedFollowUpState(initialSessionId: string | null) {
  const [steerMessages, setMessages] = useState(() =>
    readQueue(initialSessionId),
  );
  const queueRef = useRef(steerMessages);
  const ownerRef = useRef(initialSessionId);

  const setSteerMessages = useCallback(
    (update: (items: SteerItem[]) => SteerItem[]) => {
      const next = update(queueRef.current);
      queueRef.current = next;
      // Persist at the action boundary, before the browser can reload. Do not
      // write inside React state updaters, which StrictMode can replay.
      saveQueue(ownerRef.current, next);
      setMessages(next);
    },
    [],
  );

  const clearSteerMessages = useCallback(() => {
    // Navigation clears only the view; the previous session retains its queue.
    ownerRef.current = null;
    queueRef.current = [];
    setMessages([]);
  }, []);

  const restoreSteerMessages = useCallback((sessionId: string) => {
    ownerRef.current = sessionId;
    const restored = readQueue(sessionId);
    queueRef.current = restored;
    setMessages(restored);
  }, []);

  const bindSteerSession = useCallback((sessionId: string) => {
    ownerRef.current = sessionId;
    saveQueue(sessionId, queueRef.current);
  }, []);

  return {
    steerMessages,
    setSteerMessages,
    clearSteerMessages,
    restoreSteerMessages,
    bindSteerSession,
  };
}
