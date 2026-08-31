import {
  buildMessageBookmarkUrl,
  buildMessageBookmarkBody,
} from "../bookmark";

test("builds the message bookmark toggle url", () => {
  expect(buildMessageBookmarkUrl("session-1", "message-1")).toBe(
    "/api/sessions/session-1/messages/message-1/bookmark",
  );
});

test("builds a bookmark toggle body with run_id and label", () => {
  expect(
    buildMessageBookmarkBody({ run_id: "run-1", label: "季度规划大纲" }),
  ).toEqual({ run_id: "run-1", label: "季度规划大纲" });
});

test("builds a bookmark toggle body with null placeholders", () => {
  expect(buildMessageBookmarkBody()).toEqual({
    run_id: null,
    label: null,
  });
});
