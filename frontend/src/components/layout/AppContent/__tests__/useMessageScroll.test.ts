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
  getMessageScrollSessionResetState,
  getMessageUpdateScrollAction,
  getNextMessageScrollFollowStateForAtBottomChange,
  getNextMessageScrollFollowStateForBottomScroll,
  getNextMessageScrollFollowStateForUserGesture,
  getNextMessageScrollFollowStateForUserIntent,
  getNextMessageScrollFollowStateForUserScroll,
  didLatestStreamingAssistantFinish,
  highlightElementForExternalNavigation,
  scrollElementIntoViewWithRetries,
  shouldArmPendingHistoryScroll,
  shouldScrollExternalNavigationFallbackToMessage,
  shouldDeferExternalNavigationScroll,
  shouldKeepExternalNavigationPending,
  shouldFinalizeHistoryLoadScroll,
  shouldInferBatchedHistoryLoadReady,
} from "../useMessageScroll.ts";

test("clears the user-scrolled flag when virtuoso reports bottom reached", () => {
  expect(
    getNextMessageScrollFollowStateForAtBottomChange({
      state: createMessageScrollFollowState({
        userScrolledUp: true,
        autoScrollActive: true,
        streamLockActive: true,
        manualDetachFromStream: true,
      }),
      atBottom: true,
    }),
  ).toEqual({
    userScrolledUp: false,
    autoScrollActive: true,
    streamLockActive: true,
    manualDetachFromStream: true,
  });
});

test("resets follow and history state when switching sessions", () => {
  expect(getMessageScrollSessionResetState()).toEqual({
    userScrolledUp: false,
    autoScrollActive: false,
    streamLockActive: false,
    manualDetachFromStream: false,
    pendingHistoryScroll: false,
    historyScrollArmed: false,
    isNearBottom: true,
  });
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      fileKey: "revealed_files/new.txt",
      originalPath: "/tmp/new.txt",
      source: "reveal_file",
    }),
  ).toEqual({ messageIndex: 1, partIndex: 0 });
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      originalPath: "/workspace/demo-app",
      source: "reveal_project",
    }),
  ).toEqual({ messageIndex: 0, partIndex: 0 });
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      fileKey: "revealed/nested",
      originalPath: "/tmp/nested.txt",
      source: "reveal_file",
    }),
  ).toEqual({
    messageIndex: 0,
    partIndex: 0,
    anchorId: createToolPartAnchorId(createSubagentAnchorOwnerId("agent-1"), 0),
    subagentChain: ["agent-1"],
  });
});

test("finds artifact parts for file targets without reveal tool blocks", () => {
  const messages = [
    {
      id: "message-1",
      parts: [
        {
          type: "artifact" as const,
          success: true,
          artifact: {
            kind: "file" as const,
            id: "file:revealed/puppy.svg",
            name: "puppy.svg",
            path: "/workspace/puppy.svg",
            preview: {
              kind: "file" as const,
              previewKey: "revealed/puppy.svg",
              filePath: "/workspace/puppy.svg",
              s3Key: "revealed/puppy.svg",
              signedUrl: "/api/upload/file/revealed/puppy.svg",
            },
          },
        },
      ],
    },
  ];

  expect(
    findMessageIndexForExternalNavigation(messages, {
      fileKey: "revealed/puppy.svg",
      originalPath: "/workspace/puppy.svg",
      source: "reveal_file",
    }),
  ).toEqual({
    messageIndex: 0,
    partIndex: 0,
    anchorId: createToolPartAnchorId("message-1", 0),
  });
});

test("creates stable tool part anchor ids", () => {
  expect(createToolPartAnchorId("message-1", 3)).toBe("tool-part:message-1:3");
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      fileName: "report.md",
      originalPath: "/tmp/right/report.md",
      source: "reveal_file",
    }),
  ).toEqual({ messageIndex: 0, partIndex: 0 });
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      originalPath: "C:/workspace/docs/guide.md/",
      source: "reveal_file",
    }),
  ).toEqual({ messageIndex: 0, partIndex: 0 });
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      fileName: "summary.md",
      source: "reveal_file",
    }),
  ).toEqual({ messageIndex: 0, partIndex: 0 });
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      originalPath: "C:/workspace/demo-app",
      source: "reveal_project",
    }),
  ).toEqual({ messageIndex: 0, partIndex: 0 });
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

  expect(scrolled).toBe(1);
  expect(attempts).toBe(3);
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

  expect(receivedOptions).toEqual({
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

  expect(receivedOptions).toEqual({
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

  expect(attributes.get("data-external-navigation-highlighted")).toBe("true");

  await new Promise((resolve) => setTimeout(resolve, 20));

  expect(attributes.has("data-external-navigation-highlighted")).toBe(false);
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

  expect(focused).toBe(true);
  expect(receivedOptions).toEqual({ preventScroll: true });
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

  expect(focused).toBe(true);
  expect(attrs.get("tabindex")).toBe("-1");
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

  expect(resolveElement()).toBe(null);
  expect(resolveElement()).toBe(null);
  expect(resolveElement()).toBe(target);
  expect(resolveElement()).toBe(target);
  expect(scrollToMessageCalls).toBe(3);
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

  expect(
    alignElementInScroller({
      scroller,
      element,
      topOffsetPx: 20,
    }),
  ).toBe(640);
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

  expect(
    alignElementInScroller({
      scroller,
      element,
      topOffsetPx: 20,
      align: "center",
    }),
  ).toBe(470);
});

test("finds the latest message for a resolved run id", () => {
  const messages = [{ runId: "run-1" }, { runId: "run-2" }, { runId: "run-2" }];

  expect(findMessageIndexForRunId(messages, "run-2")).toBe(2);
  expect(findMessageIndexForRunId(messages, "run-9")).toBe(-1);
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

  expect(
    findRevealPartIndexInMessage(message, {
      fileKey: "revealed/second",
      originalPath: "/tmp/second.txt",
      source: "reveal_file",
    }),
  ).toBe(1);
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

  expect(
    findExternalNavigationMatchForRunId(messages, "run-blog", {
      fileName: "blog",
      originalPath: "/home/user/blog",
      source: "reveal_project",
    }),
  ).toEqual({ messageIndex: 0, partIndex: 0 });
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

  expect(
    findMessageIndexForExternalNavigation(messages, {
      fileName: "blog",
      originalPath: "/home/user/blog",
      source: "reveal_project",
    }),
  ).toEqual({ messageIndex: 0, partIndex: 0 });
});

test("waits until history loading completes before triggering the final bottom scroll", () => {
  expect(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: true,
      isLoadingHistory: true,
      messageCount: 12,
    }),
  ).toBe(false);

  expect(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: true,
      isLoadingHistory: false,
      messageCount: 12,
    }),
  ).toBe(true);
});

test("does not trigger a final history scroll when there is no pending scroll or no messages", () => {
  expect(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: false,
      isLoadingHistory: false,
      messageCount: 12,
    }),
  ).toBe(false);

  expect(
    shouldFinalizeHistoryLoadScroll({
      pendingHistoryScroll: true,
      isLoadingHistory: false,
      messageCount: 0,
    }),
  ).toBe(false);
});

test("arms the history finalize scroll only once per loading cycle", () => {
  expect(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: true,
      sessionId: "session-1",
      historyScrollArmed: false,
    }),
  ).toBe(true);

  expect(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: true,
      sessionId: "session-1",
      historyScrollArmed: true,
    }),
  ).toBe(false);

  expect(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: false,
      sessionId: "session-1",
      historyScrollArmed: false,
    }),
  ).toBe(false);

  expect(
    shouldArmPendingHistoryScroll({
      isLoadingHistory: true,
      sessionId: null,
      historyScrollArmed: false,
    }),
  ).toBe(false);
});

test("infers a batched history load when a new session receives its first messages", () => {
  expect(
    shouldInferBatchedHistoryLoadReady({
      previousSessionId: "session-1",
      sessionId: "session-2",
      previousMessageCount: 0,
      messageCount: 8,
      isLoadingHistory: false,
      externalNavigationToken: null,
    }),
  ).toBe(true);

  expect(
    shouldInferBatchedHistoryLoadReady({
      previousSessionId: "session-1",
      sessionId: "session-1",
      previousMessageCount: 7,
      messageCount: 8,
      isLoadingHistory: false,
      externalNavigationToken: null,
    }),
  ).toBe(false);

  expect(
    shouldInferBatchedHistoryLoadReady({
      previousSessionId: "session-1",
      sessionId: "session-2",
      previousMessageCount: 0,
      messageCount: 8,
      isLoadingHistory: false,
      externalNavigationToken: "reveal:file",
    }),
  ).toBe(false);
});

test("does not keep external navigation pending when the run is known but the reveal part is missing", () => {
  expect(
    shouldKeepExternalNavigationPending({
      runMessageIndex: 3,
      matchedPartIndex: -1,
    }),
  ).toBe(false);

  expect(
    shouldKeepExternalNavigationPending({
      runMessageIndex: 3,
      matchedPartIndex: 1,
    }),
  ).toBe(false);

  expect(
    shouldKeepExternalNavigationPending({
      runMessageIndex: -1,
      matchedPartIndex: -1,
    }),
  ).toBe(false);
});

test("does not defer external navigation scrolling when the run is already known", () => {
  expect(
    shouldDeferExternalNavigationScroll({
      runMessageIndex: 3,
      matchedPartIndex: -1,
    }),
  ).toBe(false);

  expect(
    shouldDeferExternalNavigationScroll({
      runMessageIndex: 3,
      matchedPartIndex: 1,
    }),
  ).toBe(false);

  expect(
    shouldDeferExternalNavigationScroll({
      runMessageIndex: -1,
      matchedPartIndex: -1,
    }),
  ).toBe(false);
});

test("still scrolls to the run message while waiting for the exact reveal part", () => {
  expect(
    shouldScrollExternalNavigationFallbackToMessage({
      runMessageIndex: 3,
      matchedPartIndex: -1,
    }),
  ).toBe(true);

  expect(
    shouldScrollExternalNavigationFallbackToMessage({
      runMessageIndex: 3,
      matchedPartIndex: 1,
    }),
  ).toBe(false);

  expect(
    shouldScrollExternalNavigationFallbackToMessage({
      runMessageIndex: -1,
      matchedPartIndex: -1,
    }),
  ).toBe(false);
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

  expect(nextState.manualDetachFromStream).toBe(true);
  expect(nextState.userScrolledUp).toBe(true);
  expect(nextState.autoScrollActive).toBe(false);
  expect(nextState.streamLockActive).toBe(false);
});

test("detaches the active mobile stream immediately on an explicit upward touch gesture", () => {
  const nextState = getNextMessageScrollFollowStateForUserGesture({
    state: {
      userScrolledUp: false,
      autoScrollActive: true,
      streamLockActive: true,
      manualDetachFromStream: false,
    },
    isMobileViewport: true,
    streamingAssistantActive: true,
  });

  expect(nextState.userScrolledUp).toBe(true);
  expect(nextState.autoScrollActive).toBe(false);
  expect(nextState.streamLockActive).toBe(false);
  expect(nextState.manualDetachFromStream).toBe(true);
});

test("detaches the active mobile stream immediately when the user starts touching the scroller", () => {
  const nextState = getNextMessageScrollFollowStateForUserIntent({
    state: {
      userScrolledUp: false,
      autoScrollActive: true,
      streamLockActive: true,
      manualDetachFromStream: false,
    },
    isMobileViewport: true,
    streamingAssistantActive: true,
  });

  expect(nextState.userScrolledUp).toBe(true);
  expect(nextState.autoScrollActive).toBe(false);
  expect(nextState.streamLockActive).toBe(false);
  expect(nextState.manualDetachFromStream).toBe(true);
});

test("detaches the active mobile stream lock even between bottom-scroll runs", () => {
  const nextState = getNextMessageScrollFollowStateForUserIntent({
    state: {
      userScrolledUp: false,
      autoScrollActive: false,
      streamLockActive: true,
      manualDetachFromStream: false,
    },
    isMobileViewport: true,
    streamingAssistantActive: true,
  });

  expect(nextState.userScrolledUp).toBe(true);
  expect(nextState.autoScrollActive).toBe(false);
  expect(nextState.streamLockActive).toBe(false);
  expect(nextState.manualDetachFromStream).toBe(true);
});

test("detaches the active desktop stream immediately on an explicit upward wheel intent", () => {
  const nextState = getNextMessageScrollFollowStateForUserIntent({
    state: {
      userScrolledUp: false,
      autoScrollActive: true,
      streamLockActive: true,
      manualDetachFromStream: false,
    },
    isMobileViewport: false,
    streamingAssistantActive: true,
  });

  expect(nextState.userScrolledUp).toBe(true);
  expect(nextState.autoScrollActive).toBe(false);
  expect(nextState.streamLockActive).toBe(false);
  expect(nextState.manualDetachFromStream).toBe(false);
});

test("detaches the active desktop stream on the first slight upward scroll", () => {
  const nextState = getNextMessageScrollFollowStateForUserScroll({
    state: {
      userScrolledUp: false,
      autoScrollActive: true,
      streamLockActive: true,
      manualDetachFromStream: false,
    },
    isMobileViewport: false,
    streamingAssistantActive: true,
    programmaticScroll: false,
    movedUp: true,
    isAwayFromBottom: false,
    deltaScrollPx: 12,
    scrollTop: 260,
  });

  expect(nextState.userScrolledUp).toBe(true);
  expect(nextState.autoScrollActive).toBe(false);
  expect(nextState.streamLockActive).toBe(false);
  expect(nextState.manualDetachFromStream).toBe(false);
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

  expect(
    getMessageUpdateScrollAction({
      previousMessages: [{ id: "assistant-1", role: "assistant" }],
      nextMessages: [{ id: "assistant-1", role: "assistant" }],
      state: settledState,
      isNearBottom: true,
      isLoadingHistory: false,
    }),
  ).toBe(null);
});

test("settles the bottom lock when the active stream finishes near the bottom", () => {
  expect(
    getMessageUpdateScrollAction({
      previousMessages: [
        { id: "assistant-1", role: "assistant", isStreaming: true },
      ],
      nextMessages: [
        { id: "assistant-1", role: "assistant", isStreaming: false },
      ],
      state: {
        userScrolledUp: false,
        autoScrollActive: false,
        streamLockActive: true,
        manualDetachFromStream: false,
      },
      isNearBottom: true,
      isLoadingHistory: false,
      shouldMaintainStreamLock: true,
    }),
  ).toBe("request-scroll-to-bottom");
});

test("does not settle the bottom lock when a detached stream finishes", () => {
  expect(
    getMessageUpdateScrollAction({
      previousMessages: [
        { id: "assistant-1", role: "assistant", isStreaming: true },
      ],
      nextMessages: [
        { id: "assistant-1", role: "assistant", isStreaming: false },
      ],
      state: {
        userScrolledUp: true,
        autoScrollActive: false,
        streamLockActive: false,
        manualDetachFromStream: true,
      },
      isNearBottom: false,
      isLoadingHistory: false,
      shouldMaintainStreamLock: false,
    }),
  ).toBe(null);
});

test("detects when the latest assistant stream finishes", () => {
  expect(
    didLatestStreamingAssistantFinish({
      previousMessages: [
        { id: "assistant-1", role: "assistant", isStreaming: true },
      ],
      nextMessages: [
        { id: "assistant-1", role: "assistant", isStreaming: false },
      ],
    }),
  ).toBe(true);

  expect(
    didLatestStreamingAssistantFinish({
      previousMessages: [
        { id: "assistant-1", role: "assistant", isStreaming: true },
      ],
      nextMessages: [
        { id: "assistant-2", role: "assistant", isStreaming: false },
      ],
    }),
  ).toBe(false);
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

  expect(reenteredState.manualDetachFromStream).toBe(false);
  expect(reenteredState.userScrolledUp).toBe(false);
  expect(reenteredState.autoScrollActive).toBe(true);
  expect(reenteredState.streamLockActive).toBe(true);
  expect(
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
  ).toBe("request-scroll-to-bottom");
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

  expect(passiveReentryState.manualDetachFromStream).toBe(true);
  expect(passiveReentryState.userScrolledUp).toBe(true);
  expect(passiveReentryState.autoScrollActive).toBe(false);
  expect(passiveReentryState.streamLockActive).toBe(false);
  expect(
    getMessageUpdateScrollAction({
      previousMessages: [{ id: "assistant-1", role: "assistant" }],
      nextMessages: [{ id: "assistant-1", role: "assistant" }],
      state: passiveReentryState,
      isNearBottom: true,
      isLoadingHistory: false,
    }),
  ).toBe(null);
});

test("local send clears the detach lock and starts a fresh follow cycle", () => {
  const detachedState = {
    userScrolledUp: true,
    autoScrollActive: false,
    streamLockActive: false,
    manualDetachFromStream: true,
  };

  expect(
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
  ).toBe("scroll-to-bottom");

  const restartedState = getNextMessageScrollFollowStateForBottomScroll({
    state: detachedState,
    streamingAssistantActive: false,
    clearManualDetachFromStream: true,
  });

  expect(restartedState.manualDetachFromStream).toBe(false);
  expect(restartedState.userScrolledUp).toBe(false);
  expect(restartedState.autoScrollActive).toBe(true);
});
