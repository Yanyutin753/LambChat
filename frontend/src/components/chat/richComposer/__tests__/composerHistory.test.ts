import { decodeComposerHistoryEntry } from "../composerHistory";
import type { ComposerSnapshot } from "../composerTypes";

test("decodes a versioned composer snapshot", () => {
  const snapshot = {
    version: 1,
    editorState: {
      root: { type: "root", version: 1, children: [] },
    },
    plainText: "hello",
  } satisfies ComposerSnapshot;

  expect(decodeComposerHistoryEntry(JSON.stringify(snapshot))).toEqual(
    snapshot,
  );
});

test("imports legacy history strings as plain text", () => {
  expect(decodeComposerHistoryEntry("legacy prompt")).toEqual({
    version: 0,
    plainText: "legacy prompt",
  });
});

test("keeps malformed JSON as recoverable legacy text", () => {
  expect(decodeComposerHistoryEntry("{broken")).toEqual({
    version: 0,
    plainText: "{broken",
  });
});

test("does not accept unknown snapshot versions", () => {
  const value = JSON.stringify({ version: 2, editorState: {} });
  expect(decodeComposerHistoryEntry(value)).toEqual({
    version: 0,
    plainText: value,
  });
});
