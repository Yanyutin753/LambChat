import type { BackendSession } from "../../../services/api/session.ts";
import {
  getExternalUnreadCountForScheduledTasks,
  getUnreadCountForScheduledTask,
  getUnreadCountForUncategorized,
  getUnreadCountForFavorites,
  getUnreadCountForProject,
  mergeUnreadUpdate,
} from "../unreadCounts.ts";

function session(
  id: string,
  unreadCount: number,
  projectId?: string | null,
  scheduledTaskId?: string | null,
): BackendSession {
  const metadata: Record<string, unknown> = {};
  if (projectId !== undefined) metadata.project_id = projectId;
  if (scheduledTaskId !== undefined) {
    metadata.scheduled_task_id = scheduledTaskId;
  }
  return {
    id,
    agent_id: "search",
    created_at: "2026-04-22T00:00:00.000Z",
    updated_at: "2026-04-22T00:00:00.000Z",
    is_active: true,
    metadata,
    unread_count: unreadCount,
  };
}

test("project unread count includes externally reported sessions", () => {
  const unreadBySession = mergeUnreadUpdate(new Map(), {
    sessionId: "unloaded-session",
    unreadCount: 3,
    projectId: "project-1",
    isFavorite: false,
  });

  expect(
    getUnreadCountForProject({
      projectId: "project-1",
      loadedSessions: [session("loaded-session", 2, "project-1")],
      unreadBySession,
    }),
  ).toBe(5);
});

test("project unread count does not double count loaded sessions", () => {
  const unreadBySession = mergeUnreadUpdate(new Map(), {
    sessionId: "loaded-session",
    unreadCount: 3,
    projectId: "project-1",
    isFavorite: false,
  });

  expect(
    getUnreadCountForProject({
      projectId: "project-1",
      loadedSessions: [session("loaded-session", 4, "project-1")],
      unreadBySession,
    }),
  ).toBe(4);
});

test("zero unread updates remove external unread entries", () => {
  const withUnread = mergeUnreadUpdate(new Map(), {
    sessionId: "session-1",
    unreadCount: 1,
    projectId: "project-1",
    isFavorite: false,
  });
  const cleared = mergeUnreadUpdate(withUnread, {
    sessionId: "session-1",
    unreadCount: 0,
    projectId: "project-1",
    isFavorite: false,
  });

  expect(cleared.has("session-1")).toBe(false);
});

test("favorite unread count only includes favorited sessions", () => {
  expect(
    getUnreadCountForFavorites(
      [
        session("favorite-session", 2, "project-1"),
        { ...session("plain-session", 3, "project-1"), metadata: {} },
        {
          ...session("favorited-session", 4, "project-2"),
          metadata: { project_id: "project-2", is_favorite: true },
        },
      ],
      new Map(),
    ),
  ).toBe(4);
});

test("favorite unread count includes external unread sessions not yet loaded", () => {
  const unreadBySession = new Map([
    [
      "favorite-external",
      { count: 3, projectId: "project-1", isFavorite: true },
    ],
    ["plain-external", { count: 5, projectId: "project-2", isFavorite: false }],
  ]);

  expect(
    getUnreadCountForFavorites(
      [
        {
          ...session("favorited-session", 4, "project-2"),
          metadata: { project_id: "project-2", is_favorite: true },
        },
      ],
      unreadBySession,
    ),
  ).toBe(7);
});

test("uncategorized unread count excludes scheduled task sessions", () => {
  const unreadBySession = new Map([
    [
      "scheduled-external",
      {
        count: 5,
        projectId: null,
        scheduledTaskId: "task-1",
        isFavorite: false,
      },
    ],
    ["plain-external", { count: 3, projectId: null, isFavorite: false }],
  ]);

  expect(
    getUnreadCountForUncategorized({
      loadedSessions: [
        session("plain-loaded", 2),
        session("scheduled-loaded", 4, null, "task-1"),
      ],
      unreadBySession,
    }),
  ).toBe(5);
});

test("scheduled task unread count includes loaded and external sessions without double counting", () => {
  const unreadBySession = mergeUnreadUpdate(new Map(), {
    sessionId: "loaded-scheduled",
    unreadCount: 9,
    projectId: null,
    scheduledTaskId: "task-1",
    isFavorite: false,
  });
  const withExternal = mergeUnreadUpdate(unreadBySession, {
    sessionId: "external-scheduled",
    unreadCount: 3,
    projectId: null,
    scheduledTaskId: "task-1",
    isFavorite: false,
  });

  expect(
    getUnreadCountForScheduledTask({
      scheduledTaskId: "task-1",
      loadedSessions: [session("loaded-scheduled", 4, null, "task-1")],
      unreadBySession: withExternal,
    }),
  ).toBe(7);
});

test("scheduled task aggregate external unread can exclude already tracked tasks", () => {
  const unreadBySession = new Map([
    [
      "tracked-task-session",
      {
        count: 4,
        projectId: null,
        scheduledTaskId: "tracked-task",
        isFavorite: false,
      },
    ],
    [
      "external-task-session",
      {
        count: 6,
        projectId: null,
        scheduledTaskId: "external-task",
        isFavorite: false,
      },
    ],
    ["plain-session", { count: 8, projectId: null, isFavorite: false }],
  ]);

  expect(
    getExternalUnreadCountForScheduledTasks(
      unreadBySession,
      new Set(["tracked-task"]),
    ),
  ).toBe(6);
});
