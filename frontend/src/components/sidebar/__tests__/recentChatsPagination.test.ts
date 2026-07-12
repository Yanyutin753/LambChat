import type { BackendSession } from "../../../services/api/session.ts";
import {
  getNextRecentChatsState,
  mergeRecentChatSessions,
} from "../recentChatsPagination.ts";

function session(id: string): BackendSession {
  return {
    id,
    agent_id: "default",
    created_at: "2026-05-18T00:00:00.000Z",
    updated_at: "2026-05-18T00:00:00.000Z",
    is_active: true,
    metadata: {},
  };
}

test("mergeRecentChatSessions appends later pages without duplicating refreshed rows", () => {
  expect(
    mergeRecentChatSessions(
      [session("newest"), session("overlap")],
      [session("overlap"), session("older")],
    ).map((item) => item.id),
  ).toEqual(["newest", "overlap", "older"]);
});

test("getNextRecentChatsState advances skip by the appended page size", () => {
  expect(
    getNextRecentChatsState({
      previousSessions: [session("a"), session("b")],
      pageSessions: [session("c"), session("d")],
      previousSkip: 2,
      reset: false,
      hasMore: true,
    }),
  ).toEqual({
    sessions: [session("a"), session("b"), session("c"), session("d")],
    skip: 4,
    hasMore: true,
  });
});

test("getNextRecentChatsState replaces sessions on reset", () => {
  expect(
    getNextRecentChatsState({
      previousSessions: [session("old")],
      pageSessions: [session("fresh")],
      previousSkip: 20,
      reset: true,
      hasMore: false,
    }),
  ).toEqual({
    sessions: [session("fresh")],
    skip: 1,
    hasMore: false,
  });
});
