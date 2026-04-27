export { useMessageScroll } from "./useMessageScroll.hook";

export {
  alignElementInScroller,
  createExternalNavigationElementResolver,
  createSubagentAnchorOwnerId,
  createToolPartAnchorId,
  findExternalNavigationMatchForRunId,
  findMessageIndexForExternalNavigation,
  findMessageIndexForRunId,
  findRevealPartIndexInMessage,
  focusElementForExternalNavigation,
  highlightElementForExternalNavigation,
  scrollElementIntoViewWithRetries,
  shouldDeferExternalNavigationScroll,
  shouldKeepExternalNavigationPending,
  shouldScrollExternalNavigationFallbackToMessage,
} from "./useMessageScroll.externalNavigation";

export {
  createMessageScrollFollowState,
  getNextMessageListSessionKey,
  getMessageScrollSessionResetState,
  getMessageUpdateScrollAction,
  getNextMessageScrollFollowStateForAtBottomChange,
  getNextMessageScrollFollowStateForBottomScroll,
  getNextMessageScrollFollowStateForUserGesture,
  getNextMessageScrollFollowStateForUserIntent,
  getNextMessageScrollFollowStateForUserScroll,
  shouldResetMessageScrollStateForSessionChange,
  shouldArmPendingHistoryScroll,
  shouldFinalizeHistoryLoadScroll,
} from "./useMessageScroll.followState";
