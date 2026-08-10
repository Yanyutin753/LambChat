import { findSlashTrigger, getSlashTokenId } from "../slashTrigger";

test.each([
  ["/wri", 4, { from: 0, to: 4, query: "wri" }],
  ["请用 /wri", 7, { from: 3, to: 7, query: "wri" }],
  ["line one\n/w", 11, { from: 9, to: 11, query: "w" }],
] as const)(
  "finds an explicit slash command in %j",
  (text, caret, expected) => {
    expect(findSlashTrigger(text, caret)).toEqual(expected);
  },
);

test.each([
  ["https://example.com", 8],
  ["a/b", 3],
  ["/home/user", 10],
  ["/skill done", 11],
  ["prefix/skill", 12],
] as const)("does not trigger for ordinary slash text in %j", (text, caret) => {
  expect(findSlashTrigger(text, caret)).toBeNull();
});

test("does not trigger when the caret is outside the command token", () => {
  expect(findSlashTrigger("/writer later", 13)).toBeNull();
});

test("builds slash token identity from the complete slash word", () => {
  expect(getSlashTokenId("node-1", "/wri", 0)).toBe("node-1:0:/wri");
  expect(getSlashTokenId("node-1", "前缀 /wri 后缀", 3)).toBe("node-1:3:/wri");
});

test("changes slash token identity when the slash word changes", () => {
  expect(getSlashTokenId("node-1", "/wri", 0)).not.toBe(
    getSlashTokenId("node-1", "/write", 0),
  );
});
