import test from "node:test";
import assert from "node:assert/strict";
import {
  createToolPartAnchorId,
  findMessageIndexForExternalNavigation,
  findRevealPartIndexInMessage,
  findMessageIndexForRunId,
  scrollElementIntoViewWithRetries,
  shouldArmPendingHistoryScroll,
  shouldFinalizeHistoryLoadScroll,
} from "./useMessageScroll.ts";

test("finds the latest reveal_file tool block for a file target", () => {
  const messages = [
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: { path: "/tmp/old.txt" },
          result: {
            key: "revealed_files/old.txt",
            name: "old.txt",
            _meta: { path: "/tmp/old.txt" },
          },
        },
      ],
    },
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: { path: "/tmp/new.txt" },
          result: {
            key: "revealed_files/new.txt",
            name: "new.txt",
            _meta: { path: "/tmp/new.txt" },
          },
        },
      ],
    },
  ];

  assert.deepEqual(
    findMessageIndexForExternalNavigation(messages, {
      fileKey: "revealed_files/new.txt",
      originalPath: "/tmp/new.txt",
      source: "reveal_file",
    }),
    { messageIndex: 1, partIndex: 0 },
  );
});

test("finds reveal_project tool blocks by original project path", () => {
  const messages = [
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_project",
          args: { project_path: "/workspace/demo-app" },
          result: {
            name: "demo-app",
            path: "/workspace/demo-app",
            template: "vanilla",
            files: {},
            file_count: 0,
          },
        },
      ],
    },
  ];

  assert.deepEqual(
    findMessageIndexForExternalNavigation(messages, {
      originalPath: "/workspace/demo-app",
      source: "reveal_project",
    }),
    { messageIndex: 0, partIndex: 0 },
  );
});

test("creates stable tool part anchor ids", () => {
  assert.equal(createToolPartAnchorId("message-1", 3), "tool-part:message-1:3");
});

test("prefers original path matching over filename fallback", () => {
  const messages = [
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: { path: "/tmp/right/report.md" },
          result: {
            key: "revealed/right-report",
            name: "report.md",
            _meta: { path: "/tmp/right/report.md" },
          },
        },
      ],
    },
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: { path: "/tmp/wrong/report.md" },
          result: {
            key: "revealed/wrong-report",
            name: "report.md",
            _meta: { path: "/tmp/wrong/report.md" },
          },
        },
      ],
    },
  ];

  assert.deepEqual(
    findMessageIndexForExternalNavigation(messages, {
      fileName: "report.md",
      originalPath: "/tmp/right/report.md",
      source: "reveal_file",
    }),
    { messageIndex: 0, partIndex: 0 },
  );
});

test("retries anchor scrolling until the target element appears", async () => {
  let attempts = 0;
  let scrolled = 0;
  const target = {
    scrollIntoView: () => {
      scrolled += 1;
    },
  };

  scrollElementIntoViewWithRetries({
    getElement: () => {
      attempts += 1;
      return attempts >= 3 ? target : null;
    },
    schedule: (callback) => setTimeout(callback, 1) as unknown as number,
    cancelSchedule: (handle) =>
      clearTimeout(handle as unknown as NodeJS.Timeout),
    maxAttempts: 5,
  });

  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.equal(scrolled, 1);
  assert.equal(attempts, 3);
});

test("finds the latest message for a resolved run id", () => {
  const messages = [{ runId: "run-1" }, { runId: "run-2" }, { runId: "run-2" }];

  assert.equal(findMessageIndexForRunId(messages, "run-2"), 2);
  assert.equal(findMessageIndexForRunId(messages, "run-9"), -1);
});

test("finds the matching reveal part inside an already resolved run message", () => {
  const message = {
    parts: [
      {
        type: "tool" as const,
        name: "reveal_file",
        args: { path: "/tmp/first.txt" },
        result: {
          key: "revealed/first",
          name: "first.txt",
          _meta: { path: "/tmp/first.txt" },
        },
      },
      {
        type: "tool" as const,
        name: "reveal_file",
        args: { path: "/tmp/second.txt" },
        result: {
          key: "revealed/second",
          name: "second.txt",
          _meta: { path: "/tmp/second.txt" },
        },
      },
    ],
  };

  assert.equal(
    findRevealPartIndexInMessage(message, {
      fileKey: "revealed/second",
      originalPath: "/tmp/second.txt",
      source: "reveal_file",
    }),
    1,
  );
});

test("waits until history loading completes before triggering the final bottom scroll", () => {
  assert.equal(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: true,
      isLoadingHistory: true,
      messageCount: 12,
    }),
    false,
  );

  assert.equal(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: true,
      isLoadingHistory: false,
      messageCount: 12,
    }),
    true,
  );
});

test("does not trigger a final history scroll when there is no pending scroll or no messages", () => {
  assert.equal(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: false,
      isLoadingHistory: false,
      messageCount: 12,
    }),
    false,
  );

  assert.equal(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: true,
      isLoadingHistory: false,
      messageCount: 0,
    }),
    false,
  );
});

test("arms the history finalize scroll only once per loading cycle", () => {
  assert.equal(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: true,
      sessionId: "session-1",
      historyScrollArmed: false,
    }),
    true,
  );

  assert.equal(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: true,
      sessionId: "session-1",
      historyScrollArmed: true,
    }),
    false,
  );

  assert.equal(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: false,
      sessionId: "session-1",
      historyScrollArmed: false,
    }),
    false,
  );

  assert.equal(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: true,
      sessionId: null,
      historyScrollArmed: false,
    }),
    false,
  );
});
