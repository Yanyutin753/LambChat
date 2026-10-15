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
  SESSIONS_READ_INVALIDATED_EVENT,
  type BackendSession,
} from "../../services/api/session";
import type { UnreadBySession } from "../../components/sidebar/unreadCounts";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../../services/api", () => ({ sessionApi: { get: mocks.get } }));
vi.mock("../useAuth", () => ({ useAuth: () => ({ user: { id: "owner" } }) }));

afterEach(cleanup);

for (const scope of [
  {},
  { sessionId: "s1" },
  { projectId: "p1" },
  { scheduledTaskId: "t1" },
]) {
  test(`read scope clears matching sidebar rows and counts ${JSON.stringify(
    scope,
  )}`, async () => {
    const sessions = [
      {
        id: "s1",
        unread_count: 2,
        updated_at: "2026-10-15T00:02:00Z",
        metadata: { project_id: "p1", scheduled_task_id: "t1" },
      },
      {
        id: "s2",
        unread_count: 1,
        updated_at: "2026-10-15T00:02:00Z",
        metadata: { project_id: "p2" },
      },
    ] as BackendSession[];
    const updateSession = vi.fn();
    mocks.get.mockImplementation(async (id: string) => ({
      ...sessions.find((session) => session.id === id),
      unread_count: 0,
    }));
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
        unreadBySession: unread,
        setUnreadBySession,
        onNewSession: vi.fn(),
        onSelectSession: vi.fn(),
        getProjectRef: () => null,
      });
      return unread;
    });
    await act(async () =>
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

for (const kind of ["project", "scheduled"] as const) {
  for (const replacement of ["before event", "during fetch"] as const) {
    for (const eventName of [SESSIONS_READ_EVENT, SESSIONS_READ_INVALIDATED_EVENT]) {
      test(`${kind} read reconciles the current child handle replaced ${replacement} (${eventName})`, async () => {
        const session = {
          id: "child-session",
          unread_count: 2,
          updated_at: "2026-10-15T00:02:00Z",
          metadata: { project_id: "p1", scheduled_task_id: "t1" },
        } as BackendSession;
        const readSession = { ...session, unread_count: 0 };
        const oldHandle = {
          sessions: replacement === "before event" ? [] : [session],
          updateSession: vi.fn(),
          prependSession: vi.fn(),
          removeSession: vi.fn(),
          refresh: async () => {},
          softRefresh: async () => {},
        };
        let visibleUnread = 2;
        const currentHandle = {
          ...oldHandle,
          sessions: [session],
          updateSession: (updated: BackendSession) => {
            visibleUnread = updated.unread_count ?? 0;
          },
        };
        const projectRefs = { current: new Map<string, typeof oldHandle>() };
        const scheduledTaskRefs = { current: new Map<string, typeof oldHandle>() };
        const childRefs = kind === "project" ? projectRefs : scheduledTaskRefs;
        childRefs.current.set("child", oldHandle);
        const emptyList = { ...oldHandle, sessions: [] };
        let resolve!: (value: BackendSession) => void;
        if (replacement === "during fetch") {
          mocks.get.mockReturnValue(new Promise<BackendSession>((done) => {
            resolve = done;
          }));
        } else {
          mocks.get.mockResolvedValue(readSession);
        }
        renderHook(() => useSessionSidebarActions({
          uncategorizedList: emptyList,
          projectRefs,
          scheduledTaskRefs,
          projects: [],
          currentSessionId: null,
          unreadBySession: new Map(),
          setUnreadBySession: vi.fn(),
          onNewSession: vi.fn(),
          onSelectSession: vi.fn(),
          getProjectRef: () => null,
        }));

        // Child useImperativeHandle replaces this map entry without a parent render.
        if (replacement === "before event") childRefs.current.set("child", currentHandle);
        await act(async () => {
          window.dispatchEvent(new CustomEvent(eventName, { detail: {} }));
          if (replacement === "during fetch") {
            childRefs.current.set("child", currentHandle);
            resolve(readSession);
          }
        });

        expect(visibleUnread).toBe(0);
        expect(oldHandle.updateSession).not.toHaveBeenCalled();
      });
    }
  }
}
