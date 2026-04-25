import { useRef, useEffect, useState, useCallback } from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import type { Message } from "../../../types";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import {
  forceScrollerToPhysicalBottom,
  getAutoScrollResumeThresholdPx,
  getAwayFromBottomThresholdPx,
  hasNewOutgoingMessage,
  shouldAutoScrollForMessageUpdate,
  shouldAutoScrollAfterViewportChange,
  startVirtuosoScrollToBottom,
} from "./messageScrollUtils";
import { parseProjectRevealSummary } from "../../chat/ChatMessage/items/revealPreviewData";
import { openSubagentPanelByAgentId } from "../../chat/ChatMessage/SubagentBlocks";
import { isPersistentToolPanelOpen } from "../../chat/ChatMessage/items/persistentToolPanelState";
import {
  createSubagentAnchorOwnerId,
  createSubagentPanelKey,
  createToolPartAnchorId,
} from "../../chat/ChatMessage/messagePartAnchors";
import { createMessageAnchorId } from "./messageOutline";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  showScrollTop: boolean;
  handleVirtuosoAtBottomChange: (atBottom: boolean) => void;
  scrollToBottom: () => void;
  scrollToTop: () => void;
}

type AutoScrollMode = "default" | "history-finalize";

export interface ExternalNavigationMatch {
  messageIndex: number;
  partIndex: number;
  anchorId?: string;
  subagentChain?: string[];
}

type MessageWithOptionalId = Pick<Message, "parts"> &
  Partial<Pick<Message, "id">>;
type MessageWithOptionalIdAndRun = MessageWithOptionalId &
  Pick<Message, "runId">;

export function findMessageIndexForRunId(
  messages: Pick<Message, "runId">[],
  targetRunId: string | null | undefined,
): number {
  if (!targetRunId) {
    return -1;
  }

  for (let index = messages.length - 1; index >= 0; index--) {
    if (messages[index]?.runId === targetRunId) {
      return index;
    }
  }

  return -1;
}

export { createSubagentAnchorOwnerId, createToolPartAnchorId };

interface ScrollElementIntoViewWithRetriesOptions {
  getElement: () => {
    scrollIntoView: (args?: ScrollIntoViewOptions) => void;
    getBoundingClientRect?: () => DOMRect | { top: number };
  } | null;
  getScroller?: () => {
    scrollTop: number;
    clientHeight: number;
    scrollHeight: number;
    getBoundingClientRect: () => DOMRect | { top: number };
  } | null;
  schedule?: (callback: () => void) => number;
  cancelSchedule?: (handle: number) => void;
  maxAttempts?: number;
  topOffsetPx?: number;
  tolerancePx?: number;
  settleAttempts?: number;
}

export function alignElementInScroller({
  scroller,
  element,
  topOffsetPx,
}: {
  scroller: {
    scrollTop: number;
    clientHeight: number;
    scrollHeight: number;
    getBoundingClientRect: () => DOMRect | { top: number };
  };
  element: {
    getBoundingClientRect: () => DOMRect | { top: number };
  };
  topOffsetPx: number;
}): number {
  const scrollerRect = scroller.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  const delta = elementRect.top - scrollerRect.top - topOffsetPx;
  const maxScrollTop = Math.max(
    0,
    scroller.scrollHeight - scroller.clientHeight,
  );
  return Math.min(maxScrollTop, Math.max(0, scroller.scrollTop + delta));
}

export function scrollElementIntoViewWithRetries({
  getElement,
  getScroller,
  schedule = (callback) => requestAnimationFrame(callback),
  cancelSchedule = (handle) => cancelAnimationFrame(handle),
  maxAttempts = 12,
  topOffsetPx = 24,
  tolerancePx = 6,
  settleAttempts = 2,
}: ScrollElementIntoViewWithRetriesOptions): () => void {
  let cancelled = false;
  let handle = 0;
  let attempt = 0;
  let settledCount = 0;

  const tryScroll = () => {
    if (cancelled) {
      return;
    }

    const element = getElement();
    if (element) {
      const scroller = getScroller?.();
      const measureElement = element.getBoundingClientRect;
      if (scroller && measureElement) {
        const currentScrollTop = scroller.scrollTop;
        const nextScrollTop = alignElementInScroller({
          scroller,
          element: {
            getBoundingClientRect: measureElement,
          },
          topOffsetPx,
        });
        const delta = Math.abs(nextScrollTop - currentScrollTop);

        if (delta <= tolerancePx) {
          settledCount += 1;
          if (settledCount >= settleAttempts) {
            return;
          }
        } else {
          settledCount = 0;
          scroller.scrollTop = nextScrollTop;
        }
      } else {
        element.scrollIntoView({ behavior: "auto", block: "start" });
        return;
      }
    } else {
      settledCount = 0;
    }

    attempt += 1;
    if (attempt >= maxAttempts) {
      return;
    }

    handle = schedule(tryScroll);
  };

  tryScroll();

  return () => {
    cancelled = true;
    if (handle) {
      cancelSchedule(handle);
    }
  };
}

interface ShouldFinalizeHistoryLoadScrollOptions {
  pendingHistoryScroll: boolean;
  isLoadingHistory: boolean;
  messageCount: number;
}

interface ShouldArmPendingHistoryScrollOptions {
  isLoadingHistory: boolean;
  sessionId?: string | null;
  historyScrollArmed: boolean;
}

export function shouldArmPendingHistoryScroll({
  isLoadingHistory,
  sessionId,
  historyScrollArmed,
}: ShouldArmPendingHistoryScrollOptions): boolean {
  return !!sessionId && isLoadingHistory && !historyScrollArmed;
}

export function shouldFinalizeHistoryLoadScroll({
  pendingHistoryScroll,
  isLoadingHistory,
  messageCount,
}: ShouldFinalizeHistoryLoadScrollOptions): boolean {
  return pendingHistoryScroll && !isLoadingHistory && messageCount > 0;
}

export function shouldKeepExternalNavigationPending({
  runMessageIndex,
  matchedPartIndex,
}: {
  runMessageIndex: number;
  matchedPartIndex: number;
}): boolean {
  return runMessageIndex !== -1 && matchedPartIndex === -1;
}

function ensureSubagentPanelsOpen(subagentChain: string[] | undefined): void {
  if (!subagentChain?.length) {
    return;
  }

  const deepestAgentId = subagentChain[subagentChain.length - 1];
  if (
    deepestAgentId &&
    isPersistentToolPanelOpen(createSubagentPanelKey(deepestAgentId))
  ) {
    return;
  }

  for (const agentId of subagentChain) {
    if (!openSubagentPanelByAgentId(agentId)) {
      break;
    }
  }
}

function parseRevealFileResult(
  result: string | Record<string, unknown> | undefined,
): {
  fileKey?: string;
  fileName?: string;
  originalPath?: string;
} | null {
  if (!result) {
    return null;
  }

  try {
    const parsed =
      typeof result === "string"
        ? (JSON.parse(result) as Record<string, unknown>)
        : result;

    if ("key" in parsed || "name" in parsed || "_meta" in parsed) {
      const meta =
        parsed._meta && typeof parsed._meta === "object"
          ? (parsed._meta as Record<string, unknown>)
          : null;
      return {
        fileKey: typeof parsed.key === "string" ? parsed.key : undefined,
        fileName: typeof parsed.name === "string" ? parsed.name : undefined,
        originalPath: typeof meta?.path === "string" ? meta.path : undefined,
      };
    }

    const file =
      parsed.type === "file_reveal" &&
      parsed.file &&
      typeof parsed.file === "object"
        ? (parsed.file as Record<string, unknown>)
        : null;

    if (!file) {
      return null;
    }

    return {
      fileKey: typeof file.s3_key === "string" ? file.s3_key : undefined,
      originalPath: typeof file.path === "string" ? file.path : undefined,
    };
  } catch {
    return null;
  }
}

function matchesRevealFilePart(
  part: NonNullable<Message["parts"]>[number],
  targetFile: ExternalNavigationTargetFile,
): boolean {
  if (part.type !== "tool" || part.name !== "reveal_file") {
    return false;
  }

  const parsedResult = parseRevealFileResult(part.result);
  const argPath =
    typeof part.args.path === "string" ? part.args.path.trim() : undefined;
  const resultPath = parsedResult?.originalPath?.trim();
  const targetPath = targetFile.originalPath?.trim();
  const resultKey = parsedResult?.fileKey?.trim();
  const targetKey = targetFile.fileKey?.trim();
  const resultName = parsedResult?.fileName?.trim();
  const targetName = targetFile.fileName?.trim();

  if (targetKey) {
    return !!resultKey && targetKey === resultKey;
  }

  if (targetPath) {
    return Boolean(
      (argPath && targetPath === argPath) ||
        (resultPath && targetPath === resultPath),
    );
  }

  if (targetName) {
    return !!resultName && targetName === resultName;
  }

  return false;
}

function matchesRevealProjectPart(
  part: NonNullable<Message["parts"]>[number],
  targetFile: ExternalNavigationTargetFile,
): boolean {
  if (part.type !== "tool" || part.name !== "reveal_project") {
    return false;
  }

  const projectPathFromArgs =
    typeof part.args.project_path === "string"
      ? part.args.project_path.trim()
      : undefined;
  const { projectPath } = parseProjectRevealSummary({
    args: part.args,
    result: part.result,
    parseErrorMessage: "",
  });
  const targetPath = targetFile.originalPath?.trim();

  return Boolean(
    targetPath &&
      ((projectPathFromArgs && targetPath === projectPathFromArgs) ||
        (projectPath && targetPath === projectPath.trim())),
  );
}

interface RevealPartMatch {
  partIndex: number;
  anchorId?: string;
  subagentChain?: string[];
}

function findRevealPartMatchInParts(
  parts: NonNullable<Message["parts"]>,
  targetFile: ExternalNavigationTargetFile,
  anchorOwnerId?: string,
  subagentChain: string[] = [],
): RevealPartMatch | null {
  for (let partIndex = parts.length - 1; partIndex >= 0; partIndex--) {
    const part = parts[partIndex];
    const matched =
      targetFile.source === "reveal_project"
        ? matchesRevealProjectPart(part, targetFile)
        : matchesRevealFilePart(part, targetFile);

    if (matched) {
      return {
        partIndex,
        ...(anchorOwnerId
          ? {
              anchorId: createToolPartAnchorId(anchorOwnerId, partIndex),
            }
          : {}),
        ...(subagentChain.length > 0
          ? {
              subagentChain: [...subagentChain],
            }
          : {}),
      };
    }

    if (part.type === "subagent" && part.parts?.length) {
      const nestedMatch = findRevealPartMatchInParts(
        part.parts,
        targetFile,
        createSubagentAnchorOwnerId(part.agent_id),
        [...subagentChain, part.agent_id],
      );
      if (nestedMatch) {
        return nestedMatch;
      }
    }
  }

  return null;
}

export function findRevealPartMatchInMessage(
  message: MessageWithOptionalId | null | undefined,
  targetFile: ExternalNavigationTargetFile | null | undefined,
): RevealPartMatch | null {
  if (!message?.parts?.length || !targetFile) {
    return null;
  }

  return findRevealPartMatchInParts(message.parts, targetFile, message.id);
}

export function findMessageIndexForExternalNavigation(
  messages: MessageWithOptionalId[],
  targetFile: ExternalNavigationTargetFile | null | undefined,
): ExternalNavigationMatch | null {
  if (!targetFile) {
    return null;
  }

  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex--
  ) {
    const partMatch = findRevealPartMatchInMessage(
      messages[messageIndex],
      targetFile,
    );
    if (partMatch) {
      return {
        messageIndex,
        ...partMatch,
      };
    }
  }

  return null;
}

export function findRevealPartIndexInMessage(
  message: MessageWithOptionalId | null | undefined,
  targetFile: ExternalNavigationTargetFile | null | undefined,
): number {
  return findRevealPartMatchInMessage(message, targetFile)?.partIndex ?? -1;
}

export function findExternalNavigationMatchForRunId(
  messages: MessageWithOptionalIdAndRun[],
  targetRunId: string | null | undefined,
  targetFile: ExternalNavigationTargetFile | null | undefined,
): ExternalNavigationMatch | null {
  if (!targetRunId || !targetFile) {
    return null;
  }

  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex--
  ) {
    if (messages[messageIndex]?.runId !== targetRunId) {
      continue;
    }

    const partMatch = findRevealPartMatchInMessage(
      messages[messageIndex],
      targetFile,
    );
    if (partMatch) {
      return {
        messageIndex,
        ...partMatch,
      };
    }
  }

  return null;
}

export function useMessageScroll(
  messages: Pick<Message, "id" | "role" | "isStreaming" | "parts" | "runId">[],
  sessionId?: string | null,
  externalNavigationToken?: string | null,
  externalNavigationTargetFile?: ExternalNavigationTargetFile | null,
  externalNavigationTargetRunId?: string | null,
  externalNavigationTargetRunPending = false,
  externalScrollToBottom = false,
  isLoadingHistory = false,
): UseMessageScrollReturn {
  const MOBILE_BOTTOM_BREATHING_ROOM_PX = 96;
  const DESKTOP_BOTTOM_BREATHING_ROOM_PX = 16;
  const isMobileViewport =
    typeof window !== "undefined" ? window.innerWidth < 640 : false;
  const bottomBreathingRoomPx = isMobileViewport
    ? MOBILE_BOTTOM_BREATHING_ROOM_PX
    : DESKTOP_BOTTOM_BREATHING_ROOM_PX;
  const awayFromBottomThresholdPx = getAwayFromBottomThresholdPx(
    isMobileViewport,
    bottomBreathingRoomPx,
  );
  const autoScrollResumeThresholdPx = getAutoScrollResumeThresholdPx(
    isMobileViewport,
    bottomBreathingRoomPx,
  );
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const virtuosoScrollerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const rafRef = useRef<number>(0);
  const viewportResizeRafRef = useRef<number>(0);
  const scrollCleanupRef = useRef<(() => void) | null>(null);
  const anchorScrollCleanupRef = useRef<(() => void) | null>(null);
  const pendingExternalNavigationRef = useRef<{
    token: string;
    targetFile: ExternalNavigationTargetFile | null;
    scrollToBottom: boolean;
  } | null>(null);
  const previousMessagesRef = useRef(messages);
  const isNearBottomRef = useRef(true);

  const userScrolledUpRef = useRef(false);
  const autoScrollActiveRef = useRef(false);
  const ignoreProgrammaticScrollUntilRef = useRef(0);
  const streamLockActiveRef = useRef(false);
  const streamingAssistantActiveRef = useRef(false);
  const pendingHistoryScrollRef = useRef(false);
  const historyLoadActiveRef = useRef(isLoadingHistory);
  const historyScrollArmedRef = useRef(false);
  const isLoadingHistoryRef = useRef(isLoadingHistory);

  const latestMessage = messages[messages.length - 1];
  const hasStreamingAssistantMessage =
    latestMessage?.role === "assistant" && latestMessage.isStreaming === true;

  useEffect(() => {
    streamingAssistantActiveRef.current = hasStreamingAssistantMessage;
  }, [hasStreamingAssistantMessage]);

  useEffect(() => {
    isLoadingHistoryRef.current = isLoadingHistory;
  }, [isLoadingHistory]);

  const handleVirtuosoAtBottomChange = useCallback((atBottom: boolean) => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setIsNearBottom(atBottom);
      isNearBottomRef.current = atBottom;
      if (atBottom) {
        setShowScrollTop(false);
        userScrolledUpRef.current = false;
      }
    });
  }, []);

  // Scroll the Footer sentinel into view — it's always in the DOM (not virtualized)
  const requestScrollToBottom = useCallback(
    (mode: AutoScrollMode = "default") => {
      const isHistoryFinalizeMode = mode === "history-finalize";
      userScrolledUpRef.current = false;
      autoScrollActiveRef.current = true;
      if (streamingAssistantActiveRef.current) {
        streamLockActiveRef.current = true;
      }
      forceScrollerToPhysicalBottom({
        scroller: virtuosoScrollerRef.current,
        footer: messagesEndRef.current,
      });
      ignoreProgrammaticScrollUntilRef.current = Date.now() + 120;
      scrollCleanupRef.current?.();
      scrollCleanupRef.current = startVirtuosoScrollToBottom({
        virtuoso: virtuosoRef.current,
        scroller: virtuosoScrollerRef.current,
        footer: messagesEndRef.current,
        preferPhysicalBottom: true,
        intervalMs: isMobileViewport ? (isHistoryFinalizeMode ? 24 : 20) : 16,
        maxAttempts: isMobileViewport
          ? isHistoryFinalizeMode
            ? 24
            : 8
          : isHistoryFinalizeMode
            ? 90
            : 15,
        observeLayoutChanges: true,
        resizeObserverTarget:
          virtuosoScrollerRef.current?.firstElementChild ??
          virtuosoScrollerRef.current,
        maxDurationMs: isMobileViewport
          ? isHistoryFinalizeMode
            ? 1200
            : 240
          : isHistoryFinalizeMode
            ? 1800
            : 500,
        settleWindowMs: isMobileViewport
          ? isHistoryFinalizeMode
            ? 140
            : 96
          : isHistoryFinalizeMode
            ? 180
            : 120,
        keepAliveWhile: () =>
          streamLockActiveRef.current && streamingAssistantActiveRef.current,
        shouldAbort: () => userScrolledUpRef.current,
        onAutoScroll: () => {
          ignoreProgrammaticScrollUntilRef.current = Date.now() + 80;
        },
        onComplete: () => {
          autoScrollActiveRef.current = false;
        },
      });
    },
    [isMobileViewport],
  );

  const scrollToBottom = useCallback(() => {
    requestScrollToBottom("default");
  }, [requestScrollToBottom]);

  const scrollToTop = useCallback(() => {
    userScrolledUpRef.current = true;
    autoScrollActiveRef.current = false;
    streamLockActiveRef.current = false;
    pendingHistoryScrollRef.current = false;
    virtuosoRef.current?.scrollTo({
      top: 0,
      behavior: "auto",
    });
    setShowScrollTop(false);
  }, []);

  // Attach scroll listener when Virtuoso Scroller mounts
  useEffect(() => {
    const scroller = virtuosoScrollerRef.current;
    if (!scroller) return;

    const lastScrollTop = { value: 0 };
    const lastScrollTime = { value: 0 };
    let timer: ReturnType<typeof setTimeout> | null = null;

    const handleScroll = () => {
      const now = Date.now();
      const scrollTop = scroller.scrollTop;
      const dt = now - lastScrollTime.value;
      const dScroll = lastScrollTop.value - scrollTop;
      const programmaticScroll =
        now <= ignoreProgrammaticScrollUntilRef.current;
      const movedUp = scrollTop < lastScrollTop.value - 2;
      const isAwayFromBottom =
        scrollTop + scroller.clientHeight <
        scroller.scrollHeight - awayFromBottomThresholdPx;

      if (
        autoScrollActiveRef.current &&
        !programmaticScroll &&
        movedUp &&
        isAwayFromBottom
      ) {
        userScrolledUpRef.current = true;
        autoScrollActiveRef.current = false;
        streamLockActiveRef.current = false;
        pendingHistoryScrollRef.current = false;
      }

      if (dt < 300 && dScroll > 30 && scrollTop > 200) {
        setShowScrollTop(true);
        userScrolledUpRef.current = true;
        autoScrollActiveRef.current = false;
        streamLockActiveRef.current = false;
        pendingHistoryScrollRef.current = false;
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => setShowScrollTop(false), 3000);
      } else if (scrollTop < 200) {
        setShowScrollTop(false);
      }

      lastScrollTop.value = scrollTop;
      lastScrollTime.value = now;
    };

    scroller.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scroller.removeEventListener("scroll", handleScroll);
      if (timer) clearTimeout(timer);
    };
  }, [awayFromBottomThresholdPx, messages.length]);

  useEffect(() => {
    if (!isMobileViewport || typeof window === "undefined") {
      return;
    }

    const viewport = window.visualViewport;
    if (!viewport) {
      return;
    }

    let previousHeight = viewport.height;
    const handleViewportChange = () => {
      if (isLoadingHistoryRef.current) {
        return;
      }

      const heightChanged = Math.abs(viewport.height - previousHeight) > 4;

      previousHeight = viewport.height;

      if (!heightChanged) {
        return;
      }

      if (
        !shouldAutoScrollAfterViewportChange({
          scroller: virtuosoScrollerRef.current,
          bottomBreathingRoomPx,
          userScrolledUp: userScrolledUpRef.current,
          autoScrollActive: autoScrollActiveRef.current,
          isNearBottom: isNearBottomRef.current,
        })
      ) {
        return;
      }

      cancelAnimationFrame(viewportResizeRafRef.current);
      viewportResizeRafRef.current = requestAnimationFrame(() => {
        scrollToBottom();
      });
    };

    viewport.addEventListener("resize", handleViewportChange);

    return () => {
      viewport.removeEventListener("resize", handleViewportChange);
      cancelAnimationFrame(viewportResizeRafRef.current);
    };
  }, [bottomBreathingRoomPx, isMobileViewport, scrollToBottom]);

  useEffect(() => {
    if (!isLoadingHistory) {
      historyLoadActiveRef.current = false;
      historyScrollArmedRef.current = false;
      return;
    }

    if (!historyLoadActiveRef.current) {
      historyLoadActiveRef.current = true;
      historyScrollArmedRef.current = false;
      pendingHistoryScrollRef.current = false;
    }

    if (
      shouldArmPendingHistoryScroll({
        isLoadingHistory,
        sessionId,
        historyScrollArmed: historyScrollArmedRef.current,
      })
    ) {
      pendingHistoryScrollRef.current = !externalNavigationToken;
      historyScrollArmedRef.current = true;
    }
  }, [sessionId, externalNavigationToken, isLoadingHistory]);

  // After history load completes, jump to the final message once instead of
  // trying to bottom-lock the list throughout the loading phase.
  useEffect(() => {
    if (!isLoadingHistory && messages.length === 0) {
      pendingHistoryScrollRef.current = false;
    }

    if (
      shouldFinalizeHistoryLoadScroll({
        pendingHistoryScroll: pendingHistoryScrollRef.current,
        isLoadingHistory,
        messageCount: messages.length,
      })
    ) {
      let raf1 = 0;
      let raf2 = 0;
      let settled = false;

      const tryScroll = () => {
        if (settled) return;
        // Virtuoso may not have mounted yet (refs still null) — retry
        if (!virtuosoRef.current || !virtuosoScrollerRef.current) {
          raf1 = requestAnimationFrame(() => {
            raf2 = requestAnimationFrame(tryScroll);
          });
          return;
        }
        settled = true;
        pendingHistoryScrollRef.current = false;
        requestScrollToBottom("history-finalize");
      };

      raf1 = requestAnimationFrame(() => {
        raf2 = requestAnimationFrame(tryScroll);
      });
      return () => {
        settled = true;
        cancelAnimationFrame(raf1);
        cancelAnimationFrame(raf2);
      };
    }
  }, [isLoadingHistory, messages.length, requestScrollToBottom]);

  useEffect(() => {
    const previousMessages = previousMessagesRef.current;
    const shouldMaintainStreamLock = streamLockActiveRef.current;

    // Virtuoso's atBottomStateChange is async (rAF), so isNearBottomRef can
    // be stale after a scroll loop finishes. Bridge the gap with a physical
    // DOM check so streaming updates don't get dropped.
    let effectiveIsNearBottom = isNearBottomRef.current;
    if (!effectiveIsNearBottom && !userScrolledUpRef.current) {
      const scroller = virtuosoScrollerRef.current;
      if (scroller) {
        effectiveIsNearBottom =
          scroller.scrollTop + scroller.clientHeight >=
          scroller.scrollHeight - autoScrollResumeThresholdPx;
      }
    }

    if (hasNewOutgoingMessage(previousMessages, messages)) {
      scrollToBottom();
    } else if (
      shouldAutoScrollForMessageUpdate({
        previousMessages,
        nextMessages: messages,
        userScrolledUp: userScrolledUpRef.current,
        autoScrollActive: autoScrollActiveRef.current,
        isNearBottom: effectiveIsNearBottom,
        isLoadingHistory,
        shouldMaintainStreamLock,
      })
    ) {
      requestScrollToBottom("default");
    }

    if (!hasStreamingAssistantMessage) {
      streamLockActiveRef.current = false;
    }

    previousMessagesRef.current = messages;
  }, [
    messages,
    requestScrollToBottom,
    scrollToBottom,
    autoScrollResumeThresholdPx,
    hasStreamingAssistantMessage,
  ]);

  useEffect(() => {
    if (externalNavigationToken) {
      pendingExternalNavigationRef.current = {
        token: externalNavigationToken,
        targetFile: externalNavigationTargetFile ?? null,
        scrollToBottom: externalScrollToBottom,
      };
    }
  }, [
    externalNavigationToken,
    externalNavigationTargetFile,
    externalScrollToBottom,
  ]);

  useEffect(() => {
    const pendingExternalNavigation = pendingExternalNavigationRef.current;
    if (!pendingExternalNavigation || messages.length === 0) {
      return;
    }

    if (!virtuosoRef.current || !virtuosoScrollerRef.current) {
      return;
    }

    if (pendingExternalNavigation.targetFile) {
      if (
        pendingExternalNavigation.targetFile.traceId &&
        externalNavigationTargetRunPending &&
        !externalNavigationTargetRunId
      ) {
        return;
      }

      const runMatch = findExternalNavigationMatchForRunId(
        messages,
        externalNavigationTargetRunId,
        pendingExternalNavigation.targetFile,
      );
      const runMessageIndex = findMessageIndexForRunId(
        messages,
        externalNavigationTargetRunId,
      );
      const contentMatch =
        !runMatch && runMessageIndex === -1
          ? findMessageIndexForExternalNavigation(
              messages,
              pendingExternalNavigation.targetFile,
            )
          : null;

      if (runMessageIndex === -1 && !contentMatch) {
        if (!isLoadingHistory) {
          pendingExternalNavigationRef.current = null;
        }
        return;
      }

      userScrolledUpRef.current = true;
      autoScrollActiveRef.current = false;
      streamLockActiveRef.current = false;
      pendingHistoryScrollRef.current = false;
      ignoreProgrammaticScrollUntilRef.current = Date.now() + 120;
      anchorScrollCleanupRef.current?.();

      const resolvedMessageIndex =
        runMatch?.messageIndex ??
        (runMessageIndex !== -1
          ? runMessageIndex
          : contentMatch?.messageIndex ?? -1);
      const resolvedMatch =
        runMatch ??
        (runMessageIndex !== -1
          ? findRevealPartMatchInMessage(
              messages[resolvedMessageIndex],
              pendingExternalNavigation.targetFile,
            )
          : contentMatch);
      const matchedPartIndex = resolvedMatch?.partIndex ?? -1;
      const shouldKeepPending = shouldKeepExternalNavigationPending({
        runMessageIndex,
        matchedPartIndex,
      });

      if (!shouldKeepPending) {
        pendingExternalNavigationRef.current = null;
      }
      const fallbackMessageAnchorId = createMessageAnchorId(
        messages[resolvedMessageIndex]!.id,
      );
      const exactAnchorId = resolvedMatch?.anchorId;
      const subagentChain = resolvedMatch?.subagentChain;
      const shouldTargetExactElement =
        matchedPartIndex !== -1 && typeof exactAnchorId === "string";

      anchorScrollCleanupRef.current = scrollElementIntoViewWithRetries({
        getElement: () => {
          virtuosoRef.current?.scrollToIndex({
            index: resolvedMessageIndex,
            align: "start",
            behavior: "auto",
          });

          ensureSubagentPanelsOpen(subagentChain);

          if (shouldTargetExactElement) {
            return document.getElementById(exactAnchorId);
          }

          return document.getElementById(fallbackMessageAnchorId);
        },
        getScroller:
          shouldTargetExactElement && !subagentChain?.length
            ? () => virtuosoScrollerRef.current
            : undefined,
        topOffsetPx: 20,
        tolerancePx: 4,
        settleAttempts: 3,
        maxAttempts: subagentChain?.length ? 36 : 24,
      });
      return;
    }

    if (pendingExternalNavigation.scrollToBottom) {
      if (isLoadingHistory) {
        return;
      }
      pendingExternalNavigationRef.current = null;
      scrollToBottom();
    }
  }, [
    messages,
    scrollToBottom,
    isLoadingHistory,
    externalNavigationTargetRunId,
    externalNavigationTargetRunPending,
    externalNavigationTargetFile,
  ]);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
      cancelAnimationFrame(viewportResizeRafRef.current);
      scrollCleanupRef.current?.();
      anchorScrollCleanupRef.current?.();
    };
  }, []);

  return {
    messagesContainerRef,
    virtuosoRef,
    virtuosoScrollerRef,
    messagesEndRef,
    isNearBottom,
    showScrollTop,
    handleVirtuosoAtBottomChange,
    scrollToBottom,
    scrollToTop,
  };
}
