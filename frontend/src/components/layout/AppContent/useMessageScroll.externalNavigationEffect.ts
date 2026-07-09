import { useEffect, type RefObject } from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import type { Message } from "../../../types";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import { createMessageAnchorId } from "./messageOutline";
import type { ScrollToBottomTimingMode } from "./messageScrollUtils";
import {
  createExternalNavigationElementResolver,
  ensureSubagentPanelsOpen,
  findExternalNavigationMatchForRunId,
  findMessageIndexForExternalNavigation,
  findMessageIndexForRunId,
  findRevealPartMatchInMessage,
  focusElementForExternalNavigation,
  highlightElementForExternalNavigation,
  scrollElementIntoViewWithRetries,
  shouldDeferExternalNavigationScroll,
  shouldKeepExternalNavigationPending,
  shouldScrollExternalNavigationFallbackToMessage,
} from "./useMessageScroll.externalNavigation";

interface PendingExternalNavigation {
  token: string;
  targetFile: ExternalNavigationTargetFile | null;
  scrollToBottom: boolean;
  targetRunId: string | null;
}

interface UseMessageScrollExternalNavigationEffectArgs {
  messages: Pick<Message, "id" | "role" | "isStreaming" | "parts" | "runId">[];
  isLoadingHistory: boolean;
  externalNavigationToken?: string | null;
  externalNavigationTargetFile?: ExternalNavigationTargetFile | null;
  externalNavigationTargetRunId?: string | null;
  externalNavigationTargetRunPending: boolean;
  externalScrollToBottom: boolean;
  virtuosoRef: RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: RefObject<HTMLDivElement | null>;
  pendingExternalNavigationRef: RefObject<PendingExternalNavigation | null>;
  userScrolledUpRef: RefObject<boolean>;
  autoScrollActiveRef: RefObject<boolean>;
  streamLockActiveRef: RefObject<boolean>;
  pendingHistoryScrollRef: RefObject<boolean>;
  ignoreProgrammaticScrollUntilRef: RefObject<number>;
  anchorScrollCleanupRef: RefObject<(() => void) | null>;
  highlightCleanupRef: RefObject<(() => void) | null>;
  requestScrollToBottom: (
    mode?: ScrollToBottomTimingMode,
    options?: {
      clearManualDetachFromStream?: boolean;
      onInitialSettle?: () => void;
      onComplete?: () => void;
    },
  ) => void;
}

/**
 * Encapsulates the two effects that resolve an external navigation request
 * (e.g. clicking an outline entry or a deep link) into a scroll/highlight
 * action against the message list. Extracted from useMessageScroll.hook.ts
 * to keep that file under the 1000-line lint ceiling without changing any
 * runtime behaviour.
 */
export function useMessageScrollExternalNavigationEffect({
  messages,
  isLoadingHistory,
  externalNavigationToken,
  externalNavigationTargetFile,
  externalNavigationTargetRunId,
  externalNavigationTargetRunPending,
  externalScrollToBottom,
  virtuosoRef,
  virtuosoScrollerRef,
  pendingExternalNavigationRef,
  userScrolledUpRef,
  autoScrollActiveRef,
  streamLockActiveRef,
  pendingHistoryScrollRef,
  ignoreProgrammaticScrollUntilRef,
  anchorScrollCleanupRef,
  highlightCleanupRef,
  requestScrollToBottom,
}: UseMessageScrollExternalNavigationEffectArgs): void {
  useEffect(() => {
    if (externalNavigationToken) {
      pendingExternalNavigationRef.current = {
        token: externalNavigationToken,
        targetFile: externalNavigationTargetFile ?? null,
        scrollToBottom: externalScrollToBottom,
        targetRunId: externalNavigationTargetRunId ?? null,
      };
    }
  }, [
    externalNavigationToken,
    externalNavigationTargetFile,
    externalNavigationTargetRunId,
    externalScrollToBottom,
    pendingExternalNavigationRef,
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
        !runMatch && runMessageIndex === -1 && !externalNavigationTargetRunId
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
      const shouldDeferScroll = shouldDeferExternalNavigationScroll({
        runMessageIndex,
        matchedPartIndex,
      });
      const shouldFallbackToMessage =
        shouldScrollExternalNavigationFallbackToMessage({
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
      let hasAnimatedToMessage = false;
      let lastHighlightedElement: HTMLElement | null = null;
      const resolveTargetElement = createExternalNavigationElementResolver({
        shouldTargetExactElement:
          shouldTargetExactElement && !shouldFallbackToMessage,
        scrollToMessageIndex: () => {
          virtuosoRef.current?.scrollToIndex({
            index: resolvedMessageIndex,
            align: "center",
            behavior: hasAnimatedToMessage ? "auto" : "smooth",
          });
          hasAnimatedToMessage = true;
        },
        getExactElement: () =>
          exactAnchorId ? document.getElementById(exactAnchorId) : null,
        getFallbackElement: () =>
          document.getElementById(fallbackMessageAnchorId),
      });

      anchorScrollCleanupRef.current = scrollElementIntoViewWithRetries({
        getElement: () => {
          ensureSubagentPanelsOpen(subagentChain);
          const element = resolveTargetElement();
          if (element && element !== lastHighlightedElement) {
            highlightCleanupRef.current?.();
            highlightCleanupRef.current = highlightElementForExternalNavigation(
              {
                element,
              },
            );
            focusElementForExternalNavigation({
              element,
            });
            lastHighlightedElement = element;
          }
          return element;
        },
        getScroller:
          shouldTargetExactElement && !subagentChain?.length
            ? () => virtuosoScrollerRef.current
            : undefined,
        topOffsetPx: 20,
        tolerancePx: 4,
        settleAttempts: 3,
        maxAttempts: subagentChain?.length ? 36 : 24,
        behavior: "smooth",
        align: "center",
      });

      if (shouldDeferScroll) {
        return;
      }
      return;
    }

    if (pendingExternalNavigation.targetRunId) {
      const runMessageIndex = findMessageIndexForRunId(
        messages,
        pendingExternalNavigation.targetRunId,
      );

      if (runMessageIndex === -1) {
        if (!isLoadingHistory) {
          pendingExternalNavigationRef.current = null;
        }
        return;
      }

      pendingExternalNavigationRef.current = null;
      userScrolledUpRef.current = true;
      autoScrollActiveRef.current = false;
      streamLockActiveRef.current = false;
      pendingHistoryScrollRef.current = false;
      ignoreProgrammaticScrollUntilRef.current = Date.now() + 120;
      anchorScrollCleanupRef.current?.();

      const messageAnchorId = createMessageAnchorId(
        messages[runMessageIndex]!.id,
      );
      let hasAnimatedToMessage = false;
      let lastHighlightedElement: HTMLElement | null = null;

      anchorScrollCleanupRef.current = scrollElementIntoViewWithRetries({
        getElement: () => {
          if (!hasAnimatedToMessage) {
            virtuosoRef.current?.scrollToIndex({
              index: runMessageIndex,
              align: "center",
              behavior: "smooth",
            });
            hasAnimatedToMessage = true;
          }
          const element = document.getElementById(messageAnchorId);
          if (element && element !== lastHighlightedElement) {
            highlightCleanupRef.current?.();
            highlightCleanupRef.current = highlightElementForExternalNavigation(
              {
                element,
              },
            );
            focusElementForExternalNavigation({
              element,
            });
            lastHighlightedElement = element;
          }
          return element;
        },
        topOffsetPx: 20,
        tolerancePx: 4,
        settleAttempts: 3,
        maxAttempts: 24,
        behavior: "smooth",
        align: "center",
      });
      return;
    }

    if (pendingExternalNavigation.scrollToBottom) {
      if (isLoadingHistory) {
        return;
      }
      pendingExternalNavigationRef.current = null;
      requestScrollToBottom("default");
    }
  }, [
    messages,
    requestScrollToBottom,
    isLoadingHistory,
    externalNavigationTargetRunId,
    externalNavigationTargetRunPending,
    externalNavigationTargetFile,
    anchorScrollCleanupRef,
    autoScrollActiveRef,
    highlightCleanupRef,
    ignoreProgrammaticScrollUntilRef,
    pendingExternalNavigationRef,
    pendingHistoryScrollRef,
    streamLockActiveRef,
    userScrolledUpRef,
    virtuosoRef,
    virtuosoScrollerRef,
  ]);
}
