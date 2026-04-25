import type { ScrollMessageLike } from "./messageScrollUtils";
import {
  hasNewOutgoingMessage,
  shouldAutoScrollForMessageUpdate,
  shouldStopAutoScrollOnUserScroll,
} from "./messageScrollUtils";

export type MessageScrollUpdateAction =
  | "scroll-to-bottom"
  | "request-scroll-to-bottom"
  | null;

export interface MessageScrollFollowState {
  userScrolledUp: boolean;
  autoScrollActive: boolean;
  streamLockActive: boolean;
  manualDetachFromStream: boolean;
}

export function createMessageScrollFollowState(
  overrides: Partial<MessageScrollFollowState> = {},
): MessageScrollFollowState {
  return {
    userScrolledUp: false,
    autoScrollActive: false,
    streamLockActive: false,
    manualDetachFromStream: false,
    ...overrides,
  };
}

export function getNextMessageScrollFollowStateForAtBottomChange({
  state,
  atBottom,
}: {
  state: MessageScrollFollowState;
  atBottom: boolean;
}): MessageScrollFollowState {
  if (!atBottom) {
    return state;
  }

  return {
    ...state,
    userScrolledUp: false,
  };
}

export function getNextMessageScrollFollowStateForBottomScroll({
  state,
  streamingAssistantActive,
  clearManualDetachFromStream = false,
}: {
  state: MessageScrollFollowState;
  streamingAssistantActive: boolean;
  clearManualDetachFromStream?: boolean;
}): MessageScrollFollowState {
  if (state.manualDetachFromStream && !clearManualDetachFromStream) {
    return state;
  }

  return {
    ...state,
    userScrolledUp: false,
    autoScrollActive: true,
    streamLockActive: streamingAssistantActive,
    manualDetachFromStream: clearManualDetachFromStream
      ? false
      : state.manualDetachFromStream,
  };
}

export function getNextMessageScrollFollowStateForUserScroll({
  state,
  isMobileViewport,
  streamingAssistantActive,
  programmaticScroll,
  movedUp,
  isAwayFromBottom,
  deltaScrollPx,
  scrollTop,
}: {
  state: MessageScrollFollowState;
  isMobileViewport: boolean;
  streamingAssistantActive: boolean;
  programmaticScroll: boolean;
  movedUp: boolean;
  isAwayFromBottom: boolean;
  deltaScrollPx: number;
  scrollTop: number;
}): MessageScrollFollowState {
  if (
    !shouldStopAutoScrollOnUserScroll({
      isMobileViewport,
      autoScrollActive: state.autoScrollActive,
      programmaticScroll,
      movedUp,
      isAwayFromBottom,
      deltaScrollPx,
      scrollTop,
    })
  ) {
    return state;
  }

  return {
    ...state,
    userScrolledUp: true,
    autoScrollActive: false,
    streamLockActive: false,
    manualDetachFromStream:
      state.manualDetachFromStream ||
      (isMobileViewport && streamingAssistantActive),
  };
}

export function getMessageUpdateScrollAction({
  previousMessages,
  nextMessages,
  state,
  isNearBottom,
  isLoadingHistory,
  shouldMaintainStreamLock,
}: {
  previousMessages: ScrollMessageLike[];
  nextMessages: ScrollMessageLike[];
  state: MessageScrollFollowState;
  isNearBottom: boolean;
  isLoadingHistory: boolean;
  shouldMaintainStreamLock?: boolean;
}): MessageScrollUpdateAction {
  if (hasNewOutgoingMessage(previousMessages, nextMessages)) {
    return "scroll-to-bottom";
  }

  if (
    shouldAutoScrollForMessageUpdate({
      previousMessages,
      nextMessages,
      userScrolledUp: state.userScrolledUp,
      autoScrollActive: state.autoScrollActive,
      isNearBottom,
      isLoadingHistory,
      shouldMaintainStreamLock,
      manualDetachActive: state.manualDetachFromStream,
    })
  ) {
    return "request-scroll-to-bottom";
  }

  return null;
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
