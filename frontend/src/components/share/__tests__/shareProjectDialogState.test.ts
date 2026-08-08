import {
  PROJECT_SHARE_SESSION_LIMIT,
  buildInitialProjectSessionSelection,
  resolveSessionTitle,
  toggleProjectSessionSelection,
} from "../shareProjectDialogState";

test("prefers top-level name when it is a string", () => {
  expect(
    resolveSessionTitle({
      name: "顶层名称",
      metadata: { title: "元数据标题" },
    }),
  ).toBe("顶层名称");
});

test("falls back to metadata.title when top-level name is missing", () => {
  expect(resolveSessionTitle({ metadata: { title: "元数据标题" } })).toBe(
    "元数据标题",
  );
});

test("returns empty string when neither name nor metadata.title is available", () => {
  expect(resolveSessionTitle({})).toBe("");
  expect(resolveSessionTitle({ metadata: {} })).toBe("");
});

test("falls back to metadata.title when top-level name is not a string", () => {
  // typeof 守卫：非字符串的 name（null / 数字等）不应被采用
  expect(
    resolveSessionTitle({ name: null, metadata: { title: "元数据标题" } }),
  ).toBe("元数据标题");
  expect(
    resolveSessionTitle({ name: 123, metadata: { title: "元数据标题" } }),
  ).toBe("元数据标题");
});

test("ignores non-string metadata.title", () => {
  expect(resolveSessionTitle({ name: null, metadata: { title: 123 } })).toBe(
    "",
  );
});

test("treats empty string name as present (does not fall back)", () => {
  // typeof "" === "string"：空串 name 仍优先，由调用方走兜底文案
  expect(
    resolveSessionTitle({ name: "", metadata: { title: "元数据标题" } }),
  ).toBe("");
});

test("handles missing metadata field gracefully", () => {
  expect(resolveSessionTitle({ name: null })).toBe("");
});

test("caps the initial partial-project selection at the backend limit", () => {
  const sessionIds = Array.from(
    { length: PROJECT_SHARE_SESSION_LIMIT + 5 },
    (_, index) => `session-${index}`,
  );

  expect(buildInitialProjectSessionSelection(sessionIds)).toEqual(
    sessionIds.slice(0, PROJECT_SHARE_SESSION_LIMIT),
  );
});

test("filters empty and duplicate session IDs from the initial selection", () => {
  expect(
    buildInitialProjectSessionSelection([
      "session-1",
      "",
      "session-1",
      "session-2",
    ]),
  ).toEqual(["session-1", "session-2"]);
});

test("does not allow selecting more sessions than the backend accepts", () => {
  const selected = Array.from(
    { length: PROJECT_SHARE_SESSION_LIMIT },
    (_, index) => `session-${index}`,
  );

  expect(toggleProjectSessionSelection(selected, "session-extra")).toEqual({
    selected,
    limitReached: true,
  });
});

test("still allows deselecting when the selection is at the limit", () => {
  const selected = Array.from(
    { length: PROJECT_SHARE_SESSION_LIMIT },
    (_, index) => `session-${index}`,
  );

  expect(toggleProjectSessionSelection(selected, "session-0")).toEqual({
    selected: selected.slice(1),
    limitReached: false,
  });
});
