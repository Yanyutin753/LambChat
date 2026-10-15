import { useCallback, useEffect, useRef } from "react";
import { getTaskCompletions } from "../../../services/api/taskCompletions";
import type {
  TaskCompletionEvent,
  TaskCompletionPage,
} from "../../../services/api/taskCompletions";

/** Checkpoints follow delivered pages; retries may duplicate, never skip a failed page. */
export async function drainTaskCompletions({
  cursor,
  loadPage,
  deliver,
  saveCursor,
  isCurrent,
  notBefore,
}: {
  cursor: string | null;
  notBefore?: number;
  loadPage: (cursor: string | null) => Promise<TaskCompletionPage>;
  deliver: (event: TaskCompletionEvent) => Promise<void>;
  saveCursor: (cursor: string) => void;
  isCurrent: () => boolean;
}): Promise<void> {
  // Keep catch-up bounded; remaining pages resume from this bookmark on the next wakeup.
  for (let pageNumber = 0; pageNumber < 10 && isCurrent(); pageNumber += 1) {
    const page = await loadPage(cursor);
    if (!isCurrent()) return;
    for (const event of page.items) {
      if (!isCurrent()) return;
      if (notBefore !== undefined && Date.parse(event.created_at) < notBefore)
        continue;
      await deliver(event);
    }
    if (!isCurrent()) return;
    if (page.cursor) saveCursor(page.cursor);
    if (!page.next_cursor || page.next_cursor === cursor) return;
    cursor = page.next_cursor;
  }
}

export function useTaskCompletionJournal(
  userId: string | undefined,
  enabled: boolean,
  deliver: (event: TaskCompletionEvent) => Promise<void>,
): () => Promise<void> {
  const restoreRef = useRef<() => Promise<void>>(async () => {});
  const deliverRef = useRef(deliver);
  deliverRef.current = deliver;
  const userRef = useRef(userId);
  userRef.current = userId;
  useEffect(() => {
    if (!enabled || !userId) return;
    let cancelled = false;
    let inFlight = false;
    let retryAttempt = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const since = new Date().toISOString();
    const key = `lambchat.taskCompletions.cursor.${userId}`;
    let cursor: string | null = null;
    try {
      cursor = localStorage.getItem(key);
    } catch {
      /* Private modes may disable storage. */
    }
    const current = () => !cancelled && userRef.current === userId;
    const restore = async () => {
      if (!current() || inFlight || document.visibilityState === "hidden")
        return;
      inFlight = true;
      try {
        await drainTaskCompletions({
          cursor,
          notBefore: Date.parse(since),
          loadPage: (position) => getTaskCompletions(position, since),
          deliver: (event) => deliverRef.current(event),
          isCurrent: current,
          saveCursor: (value) => {
            cursor = value;
            try {
              localStorage.setItem(key, value);
            } catch {
              /* Retain the bookmark for this mounted client. */
            }
          },
        });
        retryAttempt = 0;
      } catch (error) {
        if (current()) {
          console.warn(
            "[AppContent] Completion journal catch-up failed",
            error,
          );
          if (
            error &&
            typeof error === "object" &&
            "status" in error &&
            error.status === 503 &&
            retryAttempt < 3
          ) {
            retryTimer = setTimeout(
              () => {
                retryTimer = undefined;
                void restore();
              },
              2000 * 2 ** retryAttempt++,
            );
          }
        }
      } finally {
        inFlight = false;
      }
    };
    const refresh = async () => {
      if (inFlight) return;
      clearTimeout(retryTimer);
      retryTimer = undefined;
      retryAttempt = 0;
      await restore();
    };
    restoreRef.current = refresh;
    const wake = () => {
      void refresh();
    };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("online", wake);
    void restore();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      if (restoreRef.current === refresh) restoreRef.current = async () => {};
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("online", wake);
    };
  }, [enabled, userId]);
  return useCallback(() => restoreRef.current(), []);
}
