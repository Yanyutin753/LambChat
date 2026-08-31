import {
  isBookmarked,
  buildBookmarkLabel,
  deriveRunIdForJump,
  buildBookmarkNavigatePath,
} from "../bookmarks";

const bookmark = (overrides: Partial<Record<string, string | null>> = {}) => ({
  session_id: "session-1",
  message_id: "message-1",
  run_id: "run-1",
  ...overrides,
});

test("isBookmarked matches on session and message ids", () => {
  const items = [
    bookmark(),
    bookmark({ session_id: "session-2", message_id: "message-9" }),
  ];

  expect(isBookmarked(items, "session-1", "message-1")).toBe(true);
  expect(isBookmarked(items, "session-1", "message-2")).toBe(false);
  expect(isBookmarked(items, "session-2", "message-1")).toBe(false);
});

test("isBookmarked returns false for empty lists", () => {
  expect(isBookmarked([], "session-1", "message-1")).toBe(false);
});

test("buildBookmarkLabel collapses whitespace and truncates with ellipsis", () => {
  expect(
    buildBookmarkLabel("## 大纲\n\n- 第一条\n- 第二条\n继续的内容在这里"),
  ).toBe("## 大纲 - 第一条 - 第二条 继续的内容在这里");

  expect(buildBookmarkLabel("短消息")).toBe("短消息");
  expect(buildBookmarkLabel("x".repeat(100), 80)).toBe(
    `${"x".repeat(79)}…`,
  );
});

test("buildBookmarkLabel returns a fallback for blank input", () => {
  expect(buildBookmarkLabel("   \n\t  ")).toBe("");
});

test("deriveRunIdForJump prefers the stored run_id", () => {
  expect(deriveRunIdForJump(bookmark())).toBe("run-1");
});

test("deriveRunIdForJump strips the :user suffix from message ids", () => {
  expect(
    deriveRunIdForJump(bookmark({ run_id: null, message_id: "run-42:user" })),
  ).toBe("run-42");
});

test("deriveRunIdForJump gives up on opaque message ids", () => {
  expect(deriveRunIdForJump(bookmark({ run_id: null, message_id: "abc" }))).toBe(
    null,
  );
});

test("buildBookmarkNavigatePath deep links to the session and run", () => {
  expect(buildBookmarkNavigatePath(bookmark())).toBe(
    "/chat/session-1?run_id=run-1",
  );
});

test("buildBookmarkNavigatePath falls back to the session route", () => {
  expect(
    buildBookmarkNavigatePath(bookmark({ run_id: null, message_id: "abc" })),
  ).toBe("/chat/session-1");
});
