import assert from "node:assert/strict";
import test from "node:test";

import type { BackendSession } from "../../../services/api/session.ts";
import {
  getUnreadCountForFavorites,
  getUnreadCountForProject,
  mergeUnreadUpdate,
} from "../unreadCounts.ts";

function session(
  id: string,
  unreadCount: number,
  projectId?: string | null,
): BackendSession {
  return {
    id,
    agent_id: "search",
    created_at: "2026-04-22T00:00:00.000Z",
    updated_at: "2026-04-22T00:00:00.000Z",
    is_active: true,
    metadata: projectId === undefined ? {} : { project_id: projectId },
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

  assert.equal(
    getUnreadCountForProject({
      projectId: "project-1",
      loadedSessions: [session("loaded-session", 2, "project-1")],
      unreadBySession,
    }),
    5,
  );
});

test("project unread count does not double count loaded sessions", () => {
  const unreadBySession = mergeUnreadUpdate(new Map(), {
    sessionId: "loaded-session",
    unreadCount: 3,
    projectId: "project-1",
    isFavorite: false,
  });

  assert.equal(
    getUnreadCountForProject({
      projectId: "project-1",
      loadedSessions: [session("loaded-session", 4, "project-1")],
      unreadBySession,
    }),
    4,
  );
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

  assert.equal(cleared.has("session-1"), false);
});

test("favorite unread count only includes favorited sessions", () => {
  assert.equal(
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
    4,
  );
});

test("favorite unread count includes external unread sessions not yet loaded", () => {
  const unreadBySession = new Map([
    [
      "favorite-external",
      { count: 3, projectId: "project-1", isFavorite: true },
    ],
    ["plain-external", { count: 5, projectId: "project-2", isFavorite: false }],
  ]);

  assert.equal(
    getUnreadCountForFavorites(
      [
        {
          ...session("favorited-session", 4, "project-2"),
          metadata: { project_id: "project-2", is_favorite: true },
        },
      ],
      unreadBySession,
    ),
    7,
  );
});
