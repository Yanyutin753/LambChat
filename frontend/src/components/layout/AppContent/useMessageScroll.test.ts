import test from "node:test";
import assert from "node:assert/strict";
import {
  alignElementInScroller,
  createMessageScrollFollowState,
  createExternalNavigationElementResolver,
  createToolPartAnchorId,
  createSubagentAnchorOwnerId,
  findExternalNavigationMatchForRunId,
  findMessageIndexForExternalNavigation,
  findRevealPartIndexInMessage,
  findMessageIndexForRunId,
  focusElementForExternalNavigation,
  getMessageUpdateScrollAction,
  getNextMessageScrollFollowStateForAtBottomChange,
  getNextMessageScrollFollowStateForBottomScroll,
  getNextMessageScrollFollowStateForUserScroll,
  highlightElementForExternalNavigation,
  scrollElementIntoViewWithRetries,
  shouldArmPendingHistoryScroll,
  shouldScrollExternalNavigationFallbackToMessage,
  shouldDeferExternalNavigationScroll,
  shouldKeepExternalNavigationPending,
  shouldFinalizeHistoryLoadScroll,
} from "./useMessageScroll.ts";

test("clears the user-scrolled flag when virtuoso reports bottom reached", () => {
  assert.deepEqual(
    getNextMessageScrollFollowStateForAtBottomChange({
      state: createMessageScrollFollowState({
        userScrolledUp: true,
        autoScrollActive: true,
        streamLockActive: true,
        manualDetachFromStream: true,
      }),
      atBottom: true,
    }),
    {
      userScrolledUp: false,
      autoScrollActive: true,
      streamLockActive: true,
      manualDetachFromStream: true,
    },
  );
});

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

test("finds reveal_file tool blocks nested inside a subagent panel", () => {
  const messages = [
    {
      parts: [
        {
          type: "subagent" as const,
          agent_id: "agent-1",
          agent_name: "worker",
          input: "inspect file",
          depth: 1,
          parts: [
            {
              type: "tool" as const,
              name: "reveal_file",
              args: { path: "/tmp/nested.txt" },
              result: {
                key: "revealed/nested",
                name: "nested.txt",
                _meta: { path: "/tmp/nested.txt" },
              },
            },
          ],
        },
      ],
    },
  ];

  assert.deepEqual(
    findMessageIndexForExternalNavigation(messages, {
      fileKey: "revealed/nested",
      originalPath: "/tmp/nested.txt",
      source: "reveal_file",
    }),
    {
      messageIndex: 0,
      partIndex: 0,
      anchorId: createToolPartAnchorId(
        createSubagentAnchorOwnerId("agent-1"),
        0,
      ),
      subagentChain: ["agent-1"],
    },
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

test("matches reveal_file targets after normalizing path separators and trailing slashes", () => {
  const messages = [
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: { path: "C:\\workspace\\docs\\guide.md" },
          result: {
            key: "revealed/guide",
            name: "guide.md",
            _meta: { path: "C:\\workspace\\docs\\guide.md" },
          },
        },
      ],
    },
  ];

  assert.deepEqual(
    findMessageIndexForExternalNavigation(messages, {
      originalPath: "C:/workspace/docs/guide.md/",
      source: "reveal_file",
    }),
    { messageIndex: 0, partIndex: 0 },
  );
});

test("falls back to filename derived from old reveal_file path payloads", () => {
  const messages = [
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: { path: "/tmp/reports/summary.md" },
          result: {
            type: "file_reveal",
            file: {
              path: "/tmp/reports/summary.md",
              s3_key: "revealed/summary",
            },
          },
        },
      ],
    },
  ];

  assert.deepEqual(
    findMessageIndexForExternalNavigation(messages, {
      fileName: "summary.md",
      source: "reveal_file",
    }),
    { messageIndex: 0, partIndex: 0 },
  );
});

test("matches reveal_project targets after normalizing project paths", () => {
  const messages = [
    {
      parts: [
        {
          type: "tool" as const,
          name: "reveal_project",
          args: { project_path: "C:\\workspace\\demo-app\\" },
          result: {
            name: "demo-app",
            path: "C:/workspace/demo-app",
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
      originalPath: "C:/workspace/demo-app",
      source: "reveal_project",
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

test("uses smooth scrolling for external navigation targets when requested", () => {
  let receivedOptions: ScrollIntoViewOptions | undefined;

  scrollElementIntoViewWithRetries({
    getElement: () => ({
      scrollIntoView: (options) => {
        receivedOptions = options;
      },
    }),
    behavior: "smooth",
  });

  assert.deepEqual(receivedOptions, {
    behavior: "smooth",
    block: "start",
  });
});

test("uses centered scrolling for external navigation targets when requested", () => {
  let receivedOptions: ScrollIntoViewOptions | undefined;

  scrollElementIntoViewWithRetries({
    getElement: () => ({
      scrollIntoView: (options) => {
        receivedOptions = options;
      },
    }),
    behavior: "smooth",
    align: "center",
  });

  assert.deepEqual(receivedOptions, {
    behavior: "smooth",
    block: "center",
  });
});

test("marks the external navigation target temporarily for highlight styling", async () => {
  const attributes = new Map<string, string>();
  const element = {
    setAttribute: (name: string, value: string) => {
      attributes.set(name, value);
    },
    removeAttribute: (name: string) => {
      attributes.delete(name);
    },
  } as unknown as HTMLElement;

  highlightElementForExternalNavigation({
    element,
    durationMs: 5,
  });

  assert.equal(attributes.get("data-external-navigation-highlighted"), "true");

  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.equal(attributes.has("data-external-navigation-highlighted"), false);
});

test("focuses the external navigation target without triggering another scroll", () => {
  const attrs = new Map<string, string>();
  let focused = false;
  let receivedOptions: FocusOptions | undefined;
  const element = {
    tabIndex: -1,
    setAttribute: (name: string, value: string) => {
      attrs.set(name, value);
    },
    getAttribute: (name: string) => attrs.get(name) ?? null,
    focus: (options?: FocusOptions) => {
      focused = true;
      receivedOptions = options;
    },
  } as unknown as HTMLElement;

  focusElementForExternalNavigation({ element });

  assert.equal(focused, true);
  assert.deepEqual(receivedOptions, { preventScroll: true });
});

test("temporarily makes non-focusable external navigation targets focusable", () => {
  const attrs = new Map<string, string>();
  let focused = false;
  const element = {
    tabIndex: -1,
    setAttribute: (name: string, value: string) => {
      attrs.set(name, value);
    },
    getAttribute: (name: string) => attrs.get(name) ?? null,
    focus: () => {
      focused = true;
    },
  } as unknown as HTMLElement;

  focusElementForExternalNavigation({ element });

  assert.equal(focused, true);
  assert.equal(attrs.get("tabindex"), "-1");
});

test("stops re-jumping to the message top once the exact anchor appears", () => {
  let scrollToMessageCalls = 0;
  let resolverCalls = 0;
  const target = {
    scrollIntoView: () => {},
  } as HTMLElement;

  const resolveElement = createExternalNavigationElementResolver({
    shouldTargetExactElement: true,
    scrollToMessageIndex: () => {
      scrollToMessageCalls += 1;
    },
    getExactElement: () => {
      resolverCalls += 1;
      return resolverCalls >= 3 ? target : null;
    },
    getFallbackElement: () => null,
  });

  assert.equal(resolveElement(), null);
  assert.equal(resolveElement(), null);
  assert.equal(resolveElement(), target);
  assert.equal(resolveElement(), target);
  assert.equal(scrollToMessageCalls, 3);
});

test("aligns the target component relative to the virtuoso scroller", () => {
  const scroller = {
    scrollTop: 400,
    clientHeight: 500,
    scrollHeight: 2000,
    getBoundingClientRect: () => ({ top: 100 }),
  };
  const element = {
    getBoundingClientRect: () => ({ top: 360 }),
  };

  assert.equal(
    alignElementInScroller({
      scroller,
      element,
      topOffsetPx: 20,
    }),
    640,
  );
});

test("centers the target component relative to the virtuoso scroller", () => {
  const scroller = {
    scrollTop: 400,
    clientHeight: 500,
    scrollHeight: 2000,
    getBoundingClientRect: () => ({ top: 100, height: 500 }),
  };
  const element = {
    getBoundingClientRect: () => ({ top: 360, height: 120 }),
  };

  assert.equal(
    alignElementInScroller({
      scroller,
      element,
      topOffsetPx: 20,
      align: "center",
    }),
    470,
  );
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

test("matches reveal_project within the resolved run by project name before falling back to path", () => {
  const messages = [
    {
      runId: "run-blog",
      parts: [
        {
          type: "tool" as const,
          name: "reveal_project",
          args: { project_path: "/home/user/blog" },
          result: {
            type: "project_reveal",
            version: 2,
            name: "blog",
            path: "/home/user/blog",
            template: "static",
            files: {},
            file_count: 0,
          },
        },
      ],
    },
    {
      runId: "run-latest",
      parts: [
        {
          type: "tool" as const,
          name: "reveal_project",
          args: { project_path: "/home/user/blog" },
          result: {
            type: "project_reveal",
            version: 2,
            name: "杨洋的个人博客",
            path: "/home/user/blog",
            template: "static",
            files: {},
            file_count: 0,
          },
        },
      ],
    },
  ];

  assert.deepEqual(
    findExternalNavigationMatchForRunId(messages, "run-blog", {
      fileName: "blog",
      originalPath: "/home/user/blog",
      source: "reveal_project",
    }),
    { messageIndex: 0, partIndex: 0 },
  );
});

test("prefers reveal_project name matching over shared path when locating across the session", () => {
  const messages = [
    {
      runId: "run-blog",
      parts: [
        {
          type: "tool" as const,
          name: "reveal_project",
          args: { project_path: "/home/user/blog" },
          result: {
            type: "project_reveal",
            version: 2,
            name: "blog",
            path: "/home/user/blog",
            template: "static",
            files: {},
            file_count: 0,
          },
        },
      ],
    },
    {
      runId: "run-latest",
      parts: [
        {
          type: "tool" as const,
          name: "reveal_project",
          args: { project_path: "/home/user/blog" },
          result: {
            type: "project_reveal",
            version: 2,
            name: "杨洋的个人博客",
            path: "/home/user/blog",
            template: "static",
            files: {},
            file_count: 0,
          },
        },
      ],
    },
  ];

  assert.deepEqual(
    findMessageIndexForExternalNavigation(messages, {
      fileName: "blog",
      originalPath: "/home/user/blog",
      source: "reveal_project",
    }),
    { messageIndex: 0, partIndex: 0 },
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

test("does not keep external navigation pending when the run is known but the reveal part is missing", () => {
  assert.equal(
    shouldKeepExternalNavigationPending({
      runMessageIndex: 3,
      matchedPartIndex: -1,
    }),
    false,
  );

  assert.equal(
    shouldKeepExternalNavigationPending({
      runMessageIndex: 3,
      matchedPartIndex: 1,
    }),
    false,
  );

  assert.equal(
    shouldKeepExternalNavigationPending({
      runMessageIndex: -1,
      matchedPartIndex: -1,
    }),
    false,
  );
});

test("does not defer external navigation scrolling when the run is already known", () => {
  assert.equal(
    shouldDeferExternalNavigationScroll({
      runMessageIndex: 3,
      matchedPartIndex: -1,
    }),
    false,
  );

  assert.equal(
    shouldDeferExternalNavigationScroll({
      runMessageIndex: 3,
      matchedPartIndex: 1,
    }),
    false,
  );

  assert.equal(
    shouldDeferExternalNavigationScroll({
      runMessageIndex: -1,
      matchedPartIndex: -1,
    }),
    false,
  );
});

test("still scrolls to the run message while waiting for the exact reveal part", () => {
  assert.equal(
    shouldScrollExternalNavigationFallbackToMessage({
      runMessageIndex: 3,
      matchedPartIndex: -1,
    }),
    true,
  );

  assert.equal(
    shouldScrollExternalNavigationFallbackToMessage({
      runMessageIndex: 3,
      matchedPartIndex: 1,
    }),
    false,
  );

  assert.equal(
    shouldScrollExternalNavigationFallbackToMessage({
      runMessageIndex: -1,
      matchedPartIndex: -1,
    }),
    false,
  );
});

test("marks the active mobile stream as manually detached on the first intentional upward scroll", () => {
  const nextState = getNextMessageScrollFollowStateForUserScroll({
    state: {
      userScrolledUp: false,
      autoScrollActive: true,
      streamLockActive: true,
      manualDetachFromStream: false,
    },
    isMobileViewport: true,
    streamingAssistantActive: true,
    programmaticScroll: false,
    movedUp: true,
    isAwayFromBottom: false,
    deltaScrollPx: 12,
    scrollTop: 260,
  });

  assert.equal(nextState.manualDetachFromStream, true);
  assert.equal(nextState.userScrolledUp, true);
  assert.equal(nextState.autoScrollActive, false);
  assert.equal(nextState.streamLockActive, false);
});

test("does not re-arm streaming follow mode while mobile detach lock is active", () => {
  const detachedState = getNextMessageScrollFollowStateForUserScroll({
    state: {
      userScrolledUp: false,
      autoScrollActive: true,
      streamLockActive: true,
      manualDetachFromStream: false,
    },
    isMobileViewport: true,
    streamingAssistantActive: true,
    programmaticScroll: false,
    movedUp: true,
    isAwayFromBottom: false,
    deltaScrollPx: 12,
    scrollTop: 260,
  });
  const settledState = {
    ...detachedState,
    userScrolledUp: false,
  };

  assert.equal(
    getMessageUpdateScrollAction({
      previousMessages: [{ id: "assistant-1", role: "assistant" }],
      nextMessages: [{ id: "assistant-1", role: "assistant" }],
      state: settledState,
      isNearBottom: true,
      isLoadingHistory: false,
    }),
    null,
  );
});

test("explicit scrollToBottom clears the detach lock and allows follow to resume", () => {
  const reenteredState = getNextMessageScrollFollowStateForBottomScroll({
    state: {
      userScrolledUp: true,
      autoScrollActive: false,
      streamLockActive: false,
      manualDetachFromStream: true,
    },
    streamingAssistantActive: true,
    clearManualDetachFromStream: true,
  });

  assert.equal(reenteredState.manualDetachFromStream, false);
  assert.equal(reenteredState.userScrolledUp, false);
  assert.equal(reenteredState.autoScrollActive, true);
  assert.equal(reenteredState.streamLockActive, true);
  assert.equal(
    getMessageUpdateScrollAction({
      previousMessages: [{ id: "assistant-1", role: "assistant" }],
      nextMessages: [{ id: "assistant-1", role: "assistant" }],
      state: {
        ...reenteredState,
        autoScrollActive: false,
      },
      isNearBottom: true,
      isLoadingHistory: false,
    }),
    "request-scroll-to-bottom",
  );
});

test("passive viewport resize bottom-scroll does not clear the mobile detach lock", () => {
  const detachedState = {
    userScrolledUp: true,
    autoScrollActive: false,
    streamLockActive: false,
    manualDetachFromStream: true,
  };

  const passiveReentryState = getNextMessageScrollFollowStateForBottomScroll({
    state: detachedState,
    streamingAssistantActive: true,
    clearManualDetachFromStream: false,
  });

  assert.equal(passiveReentryState.manualDetachFromStream, true);
  assert.equal(passiveReentryState.userScrolledUp, true);
  assert.equal(passiveReentryState.autoScrollActive, false);
  assert.equal(passiveReentryState.streamLockActive, false);
  assert.equal(
    getMessageUpdateScrollAction({
      previousMessages: [{ id: "assistant-1", role: "assistant" }],
      nextMessages: [{ id: "assistant-1", role: "assistant" }],
      state: passiveReentryState,
      isNearBottom: true,
      isLoadingHistory: false,
    }),
    null,
  );
});

test("local send clears the detach lock and starts a fresh follow cycle", () => {
  const detachedState = {
    userScrolledUp: true,
    autoScrollActive: false,
    streamLockActive: false,
    manualDetachFromStream: true,
  };

  assert.equal(
    getMessageUpdateScrollAction({
      previousMessages: [{ id: "assistant-1", role: "assistant" }],
      nextMessages: [
        { id: "assistant-1", role: "assistant" },
        { id: "user-2", role: "user" },
      ],
      state: detachedState,
      isNearBottom: false,
      isLoadingHistory: false,
    }),
    "scroll-to-bottom",
  );

  const restartedState = getNextMessageScrollFollowStateForBottomScroll({
    state: detachedState,
    streamingAssistantActive: false,
    clearManualDetachFromStream: true,
  });

  assert.equal(restartedState.manualDetachFromStream, false);
  assert.equal(restartedState.userScrolledUp, false);
  assert.equal(restartedState.autoScrollActive, true);
});
