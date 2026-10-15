/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import {
  useSessionSidebarActions,
  type SessionListHandle,
} from "../useSessionSidebarActions";
import {
  SESSIONS_READ_EVENT,
  type BackendSession,
} from "../../services/api/session";
import type { UnreadBySession } from "../../components/sidebar/unreadCounts";

afterEach(cleanup);

for (const scope of [
  {},
  { sessionId: "s1" },
  { projectId: "p1" },
  { scheduledTaskId: "t1" },
]) {
  test(`read scope clears matching sidebar rows and counts ${JSON.stringify(
    scope,
  )}`, () => {
    const sessions = [
      {
        id: "s1",
        unread_count: 2,
        metadata: { project_id: "p1", scheduled_task_id: "t1" },
      },
      { id: "s2", unread_count: 1, metadata: { project_id: "p2" } },
    ] as BackendSession[];
    const updateSession = vi.fn();
    const list = {
      sessions,
      updateSession,
      softRefresh: vi.fn(),
    } as unknown as SessionListHandle;
    const hook = renderHook(() => {
      const [unread, setUnreadBySession] = useState<UnreadBySession>(
        new Map([
          ["s1", { count: 2, projectId: "p1", scheduledTaskId: "t1" }],
          ["s2", { count: 1, projectId: "p2" }],
        ]),
      );
      useSessionSidebarActions({
        uncategorizedList: list,
        pinnedList: list,
        projectRefs: { current: new Map() },
        scheduledTaskRefs: { current: new Map() },
        projects: [],
        currentSessionId: null,
        setUnreadBySession,
        onNewSession: vi.fn(),
        onSelectSession: vi.fn(),
        getProjectRef: () => null,
      });
      return unread;
    });
    act(() =>
      window.dispatchEvent(
        new CustomEvent(SESSIONS_READ_EVENT, { detail: scope }),
      ),
    );
    expect(hook.result.current.has("s1")).toBe(false);
    expect(hook.result.current.has("s2")).toBe(Object.keys(scope).length > 0);
    expect(updateSession).toHaveBeenCalledWith({
      ...sessions[0],
      unread_count: 0,
    });
    if (Object.keys(scope).length)
      expect(updateSession).not.toHaveBeenCalledWith({
        ...sessions[1],
        unread_count: 0,
      });
  });
}
