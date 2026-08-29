import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import type { Message } from "../../../types";
import type { AutoPreviewTarget } from "../../chat/ChatMessage/autoPreviewEligibility";
import type { RevealPreviewRequest } from "../../chat/ChatMessage/items/revealPreviewData";
import { clearFileRevealAutoOpenState } from "../../chat/ChatMessage/items/fileRevealAutoOpen";
import { clearProjectRevealAutoOpenState } from "../../chat/ChatMessage/items/projectRevealAutoOpen";
import {
  getLatestObservedCompletionAutoPreviewTarget,
  getLatestObservedCompletionRevealPreviewRequest,
} from "../../chat/ChatMessage/autoPreviewEligibility";
import { isFileLink } from "../../documents/utils";
import { getFullUrl } from "../../../services/api/config";
import { closePersistentToolPanel } from "../../chat/ChatMessage/items/persistentToolPanelState";
import { clearSidebarHistory } from "../../chat/ChatMessage/items/sidebarHistoryStore";
import { isUserReadingHistory } from "../../chat/streamFollowSignal";
import {
  createActiveRevealPreviewState,
  markRevealPreviewInteracted,
  shouldAcceptRevealPreviewOpen,
  shouldStabilizeScrollForAutoPreviewOpen,
  type ActiveRevealPreviewState,
  type RevealPreviewOpenSource,
} from "../../chat/ChatMessage/items/revealPreviewState";
import {
  getActiveRevealPreviewState,
  setActiveRevealPreviewState,
  subscribeActiveRevealPreviewState,
  updateActiveRevealPreviewState,
} from "../../chat/ChatMessage/items/activeRevealPreviewStore";
import { shouldInterceptFilePreviewLink } from "../../chat/ChatMessage/items/revealPreviewLinks";
import { shouldOpenExternalNavigationPreview } from "./externalNavigationState";
import { hasOpenRightPanel } from "../../common/rightPanelCoordinator";
import {
  getRightPanelPresentation,
  shouldAllowAutomaticRightPanel,
} from "../../../hooks/rightPanelLayout";

export interface RevealPreviewReturn {
  activePreview: RevealPreviewRequest | null;
  activePreviewAutomatic: boolean;
  handleOpenPreview: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
  handleClosePreview: (dismiss?: boolean) => void;
  handlePreviewInteraction: () => void;
  latestAutoPreview: AutoPreviewTarget | null;
}

export function useRevealPreview(
  messages: Message[],
  messagesContainerRef: React.RefObject<HTMLDivElement | null>,
  scrollToBottom: () => void,
  isNearBottom: boolean,
  sessionId: string | null,
  externalNavigationToken?: string | null,
  externalNavigationPreview?: RevealPreviewRequest | null,
  currentRunId?: string | null,
  isLoadingHistory = false,
): RevealPreviewReturn {
  const [, forcePreviewRender] = useState(0);
  const activePreviewStateRef = useRef<ActiveRevealPreviewState | null>(
    getActiveRevealPreviewState(),
  );
  const isNearBottomRef = useRef(isNearBottom);
  const autoPreviewScrollStabilizerRef = useRef<ReturnType<
    typeof setTimeout
  > | null>(null);
  const dismissedPreviewKeysRef = useRef<Set<string>>(new Set());
  const observedStreamingMessageIdsRef = useRef<Set<string>>(new Set());
  const observedStreamingSessionIdRef = useRef<string | null>(sessionId);
  const handledExternalPreviewRef = useRef<{
    token: string | null;
    sessionId: string | null;
  }>({
    token: null,
    sessionId: null,
  });
  const externalPreviewActiveRef = useRef(false);
  const activePreview = activePreviewStateRef.current?.request ?? null;
  const activePreviewAutomatic =
    activePreviewStateRef.current?.source === "auto" &&
    !activePreviewStateRef.current.userInteracted;

  if (observedStreamingSessionIdRef.current !== sessionId) {
    observedStreamingSessionIdRef.current = sessionId;
    observedStreamingMessageIdsRef.current.clear();
  }

  useEffect(() => {
    isNearBottomRef.current = isNearBottom;
  }, [isNearBottom]);

  useEffect(() => {
    const syncPreviewState = () => {
      const previousPreview = activePreviewStateRef.current;
      const nextPreview = getActiveRevealPreviewState();
      activePreviewStateRef.current = nextPreview;
      forcePreviewRender((count) => count + 1);

      if (
        shouldStabilizeScrollForAutoPreviewOpen({
          previousPreview,
          nextPreview,
          isNearBottom: isNearBottomRef.current,
        })
      ) {
        if (autoPreviewScrollStabilizerRef.current) {
          clearTimeout(autoPreviewScrollStabilizerRef.current);
        }
        autoPreviewScrollStabilizerRef.current = setTimeout(() => {
          autoPreviewScrollStabilizerRef.current = null;
          scrollToBottom();
        }, 360);
      }
    };

    const unsubscribe = subscribeActiveRevealPreviewState(syncPreviewState);
    return () => {
      unsubscribe();
      if (autoPreviewScrollStabilizerRef.current) {
        clearTimeout(autoPreviewScrollStabilizerRef.current);
        autoPreviewScrollStabilizerRef.current = null;
      }
    };
  }, [scrollToBottom]);

  const handleOpenPreview = useCallback(
    (
      preview: RevealPreviewRequest,
      source: RevealPreviewOpenSource = "manual",
    ) => {
      // Block auto-open when an external navigation preview is active
      if (source === "auto" && externalPreviewActiveRef.current) {
        return false;
      }

      if (
        source === "auto" &&
        !shouldAllowAutomaticRightPanel({
          presentation: getRightPanelPresentation(window.innerWidth),
          laneOccupied: hasOpenRightPanel(),
        })
      ) {
        return false;
      }

      const shouldOpen = shouldAcceptRevealPreviewOpen({
        activePreview: activePreviewStateRef.current,
        nextPreview: preview,
        source,
        dismissedPreviewKeys: dismissedPreviewKeysRef.current,
      });

      if (!shouldOpen) {
        return false;
      }

      if (source !== "auto") {
        dismissedPreviewKeysRef.current.delete(preview.previewKey);
      }

      setActiveRevealPreviewState(
        createActiveRevealPreviewState(preview, source),
      );
      return true;
    },
    [],
  );

  const handleClosePreview = useCallback((dismiss = true) => {
    const currentPreview = activePreviewStateRef.current;
    if (dismiss && currentPreview) {
      dismissedPreviewKeysRef.current.add(currentPreview.request.previewKey);
    }
    externalPreviewActiveRef.current = false;
    setActiveRevealPreviewState(null);
  }, []);

  const handlePreviewInteraction = useCallback(() => {
    updateActiveRevealPreviewState((current) =>
      markRevealPreviewInteracted(current),
    );
  }, []);

  // Fallback: intercept file links anywhere in the chat area
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement).closest("a[href]");
      if (!target) return;
      const href = (target as HTMLAnchorElement).getAttribute("href");
      if (!href) return;

      const fileLinkInfo = isFileLink(href);
      if (!fileLinkInfo.isFile) return;
      if (!shouldInterceptFilePreviewLink(href)) return;

      e.preventDefault();
      e.stopPropagation();

      const fullUrl = getFullUrl(href) || href;
      setActiveRevealPreviewState(
        createActiveRevealPreviewState(
          {
            kind: "file",
            previewKey: fullUrl,
            filePath: fileLinkInfo.fileName,
            signedUrl: fullUrl,
          },
          "manual",
        ),
      );
    };

    container.addEventListener("click", handleClick, true);
    return () => container.removeEventListener("click", handleClick, true);
  }, [messagesContainerRef]);

  useEffect(() => {
    dismissedPreviewKeysRef.current.clear();
    observedStreamingMessageIdsRef.current.clear();
    clearFileRevealAutoOpenState();
    clearProjectRevealAutoOpenState();
    clearSidebarHistory();
    setActiveRevealPreviewState(null);
    externalPreviewActiveRef.current = false;
    closePersistentToolPanel();
  }, [sessionId]);

  useEffect(() => {
    for (const message of messages) {
      if (message.isStreaming) {
        observedStreamingMessageIdsRef.current.add(message.id);
      }
    }
  }, [messages]);

  useEffect(() => {
    if (
      !shouldOpenExternalNavigationPreview({
        externalNavigationToken,
        externalNavigationPreview,
        handledToken: handledExternalPreviewRef.current.token,
        handledSessionId: handledExternalPreviewRef.current.sessionId,
        sessionId,
      })
    ) {
      return;
    }

    if (typeof window !== "undefined" && window.innerWidth < 640) {
      return;
    }

    if (!externalNavigationToken || !externalNavigationPreview) {
      return;
    }

    const opened = handleOpenPreview(externalNavigationPreview, "external");
    if (!opened) {
      return;
    }

    handledExternalPreviewRef.current = {
      token: externalNavigationToken,
      sessionId: sessionId ?? null,
    };
    externalPreviewActiveRef.current = true;
  }, [
    externalNavigationToken,
    externalNavigationPreview,
    handleOpenPreview,
    sessionId,
  ]);

  const latestAutoPreview = useMemo(
    () =>
      getLatestObservedCompletionAutoPreviewTarget({
        messages,
        observedStreamingMessageIds: observedStreamingMessageIdsRef.current,
        suppressAutoPreview: !!externalNavigationPreview,
        currentRunId,
      }),
    [messages, externalNavigationPreview, currentRunId],
  );

  const latestAutoPreviewRequest = useMemo(
    () =>
      getLatestObservedCompletionRevealPreviewRequest({
        messages,
        observedStreamingMessageIds: observedStreamingMessageIdsRef.current,
        suppressAutoPreview: !!externalNavigationPreview,
        currentRunId,
        allowHistoricalLatest: !isLoadingHistory,
      }),
    [messages, externalNavigationPreview, currentRunId, isLoadingHistory],
  );

  useEffect(() => {
    if (!latestAutoPreviewRequest) {
      return;
    }

    if (typeof window !== "undefined" && window.innerWidth < 640) {
      return;
    }

    // 用户上滑阅读历史时不自动弹预览：docked 面板会挤压聊天列宽打断阅读。
    // 本次自动打开静默跳过（不挂起补弹），产物仍可从消息里手动点开。
    if (isUserReadingHistory()) {
      return;
    }

    handleOpenPreview(latestAutoPreviewRequest, "auto");
  }, [handleOpenPreview, latestAutoPreviewRequest]);

  return {
    activePreview,
    activePreviewAutomatic,
    handleOpenPreview,
    handleClosePreview,
    handlePreviewInteraction,
    latestAutoPreview,
  };
}
