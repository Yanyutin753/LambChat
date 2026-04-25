import test from "node:test";
import assert from "node:assert/strict";
import {
  getExternalNavigationTargetFile,
  shouldResetExternalNavigateFlag,
  shouldScrollToBottomAfterExternalNavigation,
} from "./externalNavigationState.ts";

test("resets the external navigation flag only when present", () => {
  assert.equal(
    shouldResetExternalNavigateFlag({ externalNavigate: true }),
    true,
  );
  assert.equal(
    shouldResetExternalNavigateFlag({ externalNavigate: false }),
    false,
  );
  assert.equal(shouldResetExternalNavigateFlag({}), false);
  assert.equal(shouldResetExternalNavigateFlag(null), false);
});

test("marks external navigation requests that should scroll to bottom", () => {
  assert.equal(
    shouldScrollToBottomAfterExternalNavigation({
      externalNavigate: true,
      scrollToBottom: true,
    }),
    true,
  );
  assert.equal(
    shouldScrollToBottomAfterExternalNavigation({
      externalNavigate: true,
      scrollToBottom: false,
    }),
    false,
  );
  assert.equal(
    shouldScrollToBottomAfterExternalNavigation({
      externalNavigate: false,
      scrollToBottom: true,
    }),
    false,
  );
  assert.equal(shouldScrollToBottomAfterExternalNavigation(null), false);
});

test("extracts the target file only for external navigation", () => {
  assert.deepEqual(
    getExternalNavigationTargetFile({
      externalNavigate: true,
      targetFile: {
        fileId: "file-123",
        originalPath: "/tmp/demo.txt",
        source: "reveal_file",
      },
    }),
    {
      fileId: "file-123",
      originalPath: "/tmp/demo.txt",
      source: "reveal_file",
    },
  );
  assert.equal(
    getExternalNavigationTargetFile({
      externalNavigate: true,
      targetFile: {},
    }),
    null,
  );
  assert.equal(
    getExternalNavigationTargetFile({
      externalNavigate: false,
      targetFile: {
        fileId: "file-123",
      },
    }),
    null,
  );
  assert.equal(getExternalNavigationTargetFile(null), null);
});
