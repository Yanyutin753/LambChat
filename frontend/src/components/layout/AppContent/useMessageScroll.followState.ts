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

export interface MessageScrollSessionResetState
  extends MessageScrollFollowState {
  pendingHistoryScroll: boolean;
  historyScrollArmed: boolean;
  isNearBottom: boolean;
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

export function getMessageScrollSessionResetState(): MessageScrollSessionResetState {
  return {
    ...createMessageScrollFollowState(),
    pendingHistoryScroll: false,
    historyScrollArmed: false,
    isNearBottom: true,
  };
}

export function shouldResetMessageScrollStateForSessionChange({
  previousSessionId,
  sessionId,
  messageCount,
}: {
  previousSessionId?: string | null;
  sessionId?: string | null;
  messageCount: number;
}): boolean {
  if (previousSessionId === sessionId) {
    return false;
  }

  if (previousSessionId == null && sessionId && messageCount > 0) {
    return false;
  }

  return true;
}

export function getNextMessageListSessionKey({
  previousSessionId,
  sessionId,
  messageCount,
  previousKey,
}: {
  previousSessionId?: string | null;
  sessionId?: string | null;
  messageCount: number;
  previousKey: string;
}): string {
  if (
    !shouldResetMessageScrollStateForSessionChange({
      previousSessionId,
      sessionId,
      messageCount,
    })
  ) {
    return previousKey;
  }

  return sessionId ?? "__new_session__";
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

export function getNextMessageScrollFollowStateForUserIntent({
  state,
  isMobileViewport,
  streamingAssistantActive,
}: {
  state: MessageScrollFollowState;
  isMobileViewport: boolean;
  streamingAssistantActive: boolean;
}): MessageScrollFollowState {
  const hasActiveStreamFollow =
    state.autoScrollActive ||
    (state.streamLockActive && streamingAssistantActive);

  if (!hasActiveStreamFollow) {
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

export function getNextMessageScrollFollowStateForUserGesture({
  state,
  isMobileViewport,
  streamingAssistantActive,
}: {
  state: MessageScrollFollowState;
  isMobileViewport: boolean;
  streamingAssistantActive: boolean;
}): MessageScrollFollowState {
  const hasActiveStreamFollow =
    state.autoScrollActive ||
    (state.streamLockActive && streamingAssistantActive);

  if (!hasActiveStreamFollow) {
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
  const hasActiveStreamFollow =
    state.autoScrollActive ||
    (state.streamLockActive && streamingAssistantActive);

  if (
    !shouldStopAutoScrollOnUserScroll({
      isMobileViewport,
      autoScrollActive: hasActiveStreamFollow,
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

interface ShouldInferBatchedHistoryLoadReadyOptions {
  previousSessionId?: string | null;
  sessionId?: string | null;
  previousMessageCount: number;
  messageCount: number;
  isLoadingHistory: boolean;
  externalNavigationToken?: string | null;
}

interface ShouldStartHistoryScrollSettlingOptions {
  pendingHistoryScroll: boolean;
  isLoadingHistory: boolean;
  messageCount: number;
  externalNavigationToken?: string | null;
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

export function shouldInferBatchedHistoryLoadReady({
  previousSessionId,
  sessionId,
  previousMessageCount,
  messageCount,
  isLoadingHistory,
  externalNavigationToken,
}: ShouldInferBatchedHistoryLoadReadyOptions): boolean {
  return (
    previousSessionId !== sessionId &&
    !!sessionId &&
    previousMessageCount === 0 &&
    messageCount > 0 &&
    !isLoadingHistory &&
    !externalNavigationToken
  );
}

export function shouldStartHistoryScrollSettling({
  pendingHistoryScroll,
  isLoadingHistory,
  messageCount,
  externalNavigationToken,
}: ShouldStartHistoryScrollSettlingOptions): boolean {
  return (
    pendingHistoryScroll &&
    !isLoadingHistory &&
    messageCount > 0 &&
    !externalNavigationToken
  );
}
