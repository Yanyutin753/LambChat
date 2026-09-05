/**
 * Main useAgent hook
 * Provides agent communication, message management, and SSE streaming
 */

import { useState, useCallback, useRef, useEffect } from "react";
import toast from "react-hot-toast";
import i18n from "../i18n";
import type { Message, ConnectionStatus, MessageAttachment } from "../types";
import { sessionApi, type BackendSession } from "../services/api";
import { feedbackApi } from "../services/api/feedback";
import { useAuth } from "../hooks/useAuth";
import { Permission } from "../types/auth";
import {
  type UseAgentOptions,
  type SubagentStackItem,
  type HistoryEvent,
  type UseAgentReturn,
  type ChatSubmissionCallbacks,
} from "./useAgent/types";
import { applyRecommendQuestionsToMessages } from "./useAgent/recommendQuestionsUpdate";
import { useChatRuntimeStates } from "./useAgent/loadingStates";
import {
  reconstructMessagesFromEvents,
  getLastEventTimestamp,
  prepareMessagesForRunningRun,
  extractGoalFromEvents,
  extractGoalsByRunFromEvents,
  createScheduledTaskApprovalLookup,
} from "./useAgent/historyLoader";
import { clearAllLoadingStates } from "./useAgent/messageParts";
import { type EventHandlerContext } from "./useAgent/eventHandlers";
import {
  connectToSSE,
  clearReconnectTimeout,
  useSSEReconnect,
  type SSEConnectionContext,
} from "./useAgent/sseConnection";
import { createOptimisticMessagesForSend } from "./useAgent/optimisticMessages";
import { startQueuePositionPolling } from "./useAgent/queuePolling";
import {
  useSteerQueue,
  useSteerFollowUpPromotion,
} from "./useAgent/steerQueue";
import { getValidAccessToken } from "../services/api/tokenManager";
import { resolveRunEnabledSkills } from "./useAgent/runSkillOverrides";
import { planGoalSubmission } from "./useAgent/goalCommands";
import { translateApiError } from "../utils/backendErrors";
import { dispatchSessionTitleUpdated } from "../utils/sessionTitleEvents";
import { useAgentList } from "./useAgent/agentList";
import {
  notifySubmissionAccepted,
  notifySubmissionRejected,
} from "./useAgent/submissionNotifications";
import {
  applyFeedbackToMessages,
  resolveHistoryStreamRunId,
} from "./useAgent/historyLoadState";
import { HISTORY_TRACE_PAGE_SIZE } from "./useAgent/historyPagination";
import { useHistoryTracePagination } from "./useAgent/historyTracePagination";
import { extractSessionConfig } from "./useAgent/sessionConfig";
import { useAutoModeSetting } from "./useAgent/autoModeSetting";

export function useAgent(options?: UseAgentOptions): UseAgentReturn {
  const { hasAnyPermission } = useAuth();
  const canReadFeedback = hasAnyPermission([
    Permission.FEEDBACK_READ,
    Permission.FEEDBACK_WRITE,
  ]);

  // State（messages + 运行态簇；簇实现下沉 loadingStates.ts 控行数红线）
  const [messages, setMessages] = useState<Message[]>([]);
  const {
    isLoading, setIsLoading, isLoadingHistory, setIsLoadingHistory,
    historyLoadGeneration, setHistoryLoadGeneration, sessionId, setSessionId,
    currentProjectId, setCurrentProjectId, error, setError,
    connectionStatus, setConnectionStatus, currentRunId, setCurrentRunId,
    newlyCreatedSession, setNewlyCreatedSession, isInitializingSandbox,
    setIsInitializingSandbox,
    sandboxError, setSandboxError, selectedTeamId, setSelectedTeamId,
    activeGoal, setActiveGoal, goalsByRunId, setGoalsByRunId,
    goalModeEnabled, setGoalModeEnabled,
  } = useChatRuntimeStates();
  const [autoModeEnabled, setAutoModeEnabled] = useAutoModeSetting();

  // Refs for connection management
  const abortControllerRef = useRef<AbortController | null>(null);
  const historyAbortControllerRef = useRef<AbortController | null>(null);
  const sseGenerationRef = useRef(0);
  const pendingProjectIdRef = useRef<string | null>(null);
  const autoExpandProjectIdRef = useRef<string | null>(null);
  const isConnectingRef = useRef(false);
  const isLoadingHistoryRef = useRef(false);
  const isSendingRef = useRef(false);
  const loadHistoryRequestIdRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const retryCountRef = useRef(0);

  // Track processed event IDs to prevent duplicates
  const processedEventIdsRef = useRef<Set<string>>(new Set());

  // Track last event timestamp from history
  const lastHistoryTimestampRef = useRef<Date | null>(null);

  // Subagent tracking stack
  const activeSubagentStackRef = useRef<SubagentStackItem[]>([]);

  // Current streaming message ID
  const streamingMessageIdRef = useRef<string | null>(null);

  // Flag for reconnect from history
  const isReconnectFromHistoryRef = useRef<boolean>(false);

  // Stream version to invalidate stale SSE events after clearMessages
  const streamVersionRef = useRef(0);

  // Keep sessionId/runId in ref for closure access
  const sessionIdRef = useRef<string | null>(null);
  const currentRunIdRef = useRef<string | null>(null);
  const messagesRef = useRef<Message[]>([]);
  const sendMessageRef = useRef<
    | ((content: string, attachments?: MessageAttachment[]) => Promise<void>)
    | null
  >(null);
  const deferredSteersRef = useRef<
    Array<{ content: string; id: string; attachments?: MessageAttachment[] }>
  >([]);
  const followUpSteerIdsRef = useRef(new Set<string>());
  const cancelledSteerIdsRef = useRef(new Set<string>());

  const removeDeferredSteer = useCallback(
    (content: string, messageId?: string) => {
      const id = messageId;
      if (id) {
        cancelledSteerIdsRef.current.add(id);
        followUpSteerIdsRef.current.delete(id);
      }
      deferredSteersRef.current = deferredSteersRef.current.filter((item) =>
        id ? item.id !== id : item.content !== content,
      );
    },
    [],
  );

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);
  const steerQueue = useSteerQueue({
    sessionIdRef,
    deferSteer: (content, id, attachments) => {
      deferredSteersRef.current.push({ content, id, attachments });
    },
    removeDeferredSteer,
  });
  const { markSteerDelivered, clearSteerMessages, clearSteer, hydrateSteers } =
    steerQueue;

  useEffect(() => {
    currentRunIdRef.current = currentRunId;
  }, [currentRunId]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // 历史回放查到已决的 scheduled-task 审批时，补收尾对应 ask_human pill（详见 historyLoader）
  // eslint-disable-next-line react-hooks/exhaustive-deps -- 工厂仅依赖 useState 的稳定 setter
  const onApprovalLookup = useCallback(createScheduledTaskApprovalLookup(setMessages), []);

  // History trace-window pagination (older pages prepend on scroll)
  const {
    hasMoreHistoryTraces,
    isLoadingOlderHistory,
    recordFirstWindow,
    recordFeedback,
    loadOlderHistory,
    reset: resetHistoryPagination,
  } = useHistoryTracePagination({
    options,
    sessionIdRef,
    isLoadingHistoryRef,
    processedEventIdsRef,
    messagesRef,
    streamingMessageIdRef,
    setMessages,
    setGoalsByRunId,
    onApprovalLookup,
  });

  // Create event handler context
  const createEventHandlerContext = useCallback(
    (): EventHandlerContext => ({
      options,
      sessionIdRef,
      processedEventIdsRef,
      lastHistoryTimestampRef,
      activeSubagentStackRef,
      streamVersionRef,
      currentRunIdRef,
      setCurrentRunId,
      setSessionId,
      setMessages,
      markSteerDelivered,
      setConnectionStatus: (status) =>
        setConnectionStatus(status as ConnectionStatus),
      setIsInitializingSandbox,
      setSandboxError,
      setActiveGoal,
      setGoalsByRunId,
    }),
    [options, markSteerDelivered],
  );

  // Create SSE connection context
  const createSSEContext = useCallback(
    (): SSEConnectionContext => ({
      ...createEventHandlerContext(),
      abortControllerRef,
      sseGenerationRef,
      isConnectingRef,
      streamingMessageIdRef,
      reconnectTimeoutRef,
      retryCountRef,
      messagesRef,
    }),
    [createEventHandlerContext],
  );

  // Agent list loading and default agent selection
  const hasActiveMessages = useCallback(
    () => messagesRef.current.length > 0,
    [],
  );
  const {
    agents,
    currentAgent,
    setCurrentAgent,
    agentsLoading,
    allowedModelIds,
    fetchAgents,
  } = useAgentList(hasActiveMessages);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      historyAbortControllerRef.current?.abort();
      sseGenerationRef.current += 1;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      clearReconnectTimeout(reconnectTimeoutRef);
    };
  }, []);

  // Load message history from backend
  const loadHistory = useCallback(
    async (targetSessionId: string, targetRunId?: string) => {
      loadHistoryRequestIdRef.current += 1;
      const requestId = loadHistoryRequestIdRef.current;
      setHistoryLoadGeneration(requestId);
      const isStaleHistoryLoad = () =>
        requestId !== loadHistoryRequestIdRef.current || signal.aborted;

      historyAbortControllerRef.current?.abort();
      const historyAbortController = new AbortController();
      historyAbortControllerRef.current = historyAbortController;
      const signal = historyAbortController.signal;
      sseGenerationRef.current += 1;

      if (isLoadingHistoryRef.current) {
        console.log(
          "[loadHistory] Switching to new session, aborting previous load...",
        );
      }
      isLoadingHistoryRef.current = true;
      setIsLoadingHistory(true);

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      isConnectingRef.current = false;
      streamingMessageIdRef.current = null;
      clearReconnectTimeout(reconnectTimeoutRef);

      setIsLoading(true);
      setMessages([]);
      // A history load replaces the rendered conversation. Drop any optimistic
      // steer entries so they cannot survive a session switch or manual refresh.
      clearSteerMessages();
      deferredSteersRef.current = [];
      followUpSteerIdsRef.current.clear();
      cancelledSteerIdsRef.current.clear();
      setError(null);

      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;
      resetHistoryPagination();
      void sessionApi.markRead(targetSessionId).catch(() => {});
      const feedbackPromise = canReadFeedback
        ? feedbackApi
            .list(0, 100, undefined, undefined, targetSessionId)
            .catch((e) => {
              console.warn("[loadHistory] Failed to load feedback:", e);
              return null;
            })
        : Promise.resolve(null);

      // Clear approvals before loading new session
      options?.onClearApprovals?.(targetSessionId);

      try {
        const [sessionData, eventsData] = await Promise.all([
          sessionApi.get(targetSessionId, { signal }),
          sessionApi.getEvents(targetSessionId, {
            include_active_user_message: true,
            compact_message_chunks: true,
            // 首屏只取最近一页轮次，更早的在向上滚动时按游标分页加载
            trace_limit: HISTORY_TRACE_PAGE_SIZE,
            signal,
          }),
        ]);
        if (isStaleHistoryLoad()) return null;

        const pendingSteersData = await sessionApi
          .getPendingSteers(targetSessionId)
          .catch((error) => {
            console.warn(
              "[loadHistory] Failed to restore pending steers:",
              error,
            );
            return { session_id: targetSessionId, items: [] };
          });
        hydrateSteers(pendingSteersData.items);

        if (sessionData) {
          if (sessionData.name) {
            dispatchSessionTitleUpdated({
              sessionId: targetSessionId,
              title: sessionData.name,
            });
          }
          setSessionId(targetSessionId);
          setCurrentProjectId(
            (sessionData.metadata?.project_id as string) || null,
          );

          const currentRunId =
            targetRunId ||
            (sessionData.metadata?.current_run_id as string) ||
            null;

          const sessionConfig = extractSessionConfig(sessionData);
          setGoalModeEnabled(false);

          const historyEvents = (eventsData.events || []) as HistoryEvent[];
          recordFirstWindow(eventsData);
          let reconstructedMessages = reconstructMessagesFromEvents(
            historyEvents,
            processedEventIdsRef.current,
            {
              options,
              activeSubagentStack: activeSubagentStackRef.current,
              onApprovalLookup,
            },
          );
          const lastTimestamp = getLastEventTimestamp(historyEvents);
          lastHistoryTimestampRef.current = lastTimestamp;

          const restoredGoal = extractGoalFromEvents(historyEvents);
          const restoredGoalsByRun = extractGoalsByRunFromEvents(historyEvents);
          const streamRunId = resolveHistoryStreamRunId(
            eventsData.stream_run_id,
            targetRunId,
          );
          let streamingMessageId: string | null = null;
          if (streamRunId) {
            const prepared = prepareMessagesForRunningRun(
              reconstructedMessages,
              streamRunId,
              undefined,
              messagesRef.current,
            );
            reconstructedMessages = prepared.messages;
            streamingMessageId = prepared.streamingMessageId;
          }

          if (isStaleHistoryLoad()) return null;
          setCurrentRunId(currentRunId);
          setActiveGoal(restoredGoal);
          setGoalsByRunId(restoredGoalsByRun);
          setMessages(reconstructedMessages);

          void feedbackPromise.then((feedbackList) => {
            if (!feedbackList || isStaleHistoryLoad()) return;
            recordFeedback(feedbackList.items);
            setMessages((previous) =>
              applyFeedbackToMessages(previous, feedbackList.items),
            );
          });

          if (streamRunId && streamingMessageId) {
            isReconnectFromHistoryRef.current = false;
            const ctx = createSSEContext();
            void connectToSSE(
              targetSessionId,
              streamRunId,
              streamingMessageId,
              ctx,
            ).catch((e) => {
              console.warn("[loadHistory] SSE reconnect failed:", e);
            });
          }

          return sessionConfig;
        }

        // A deleted or inaccessible session must not look like an empty,
        // successfully loaded conversation.
        if (!isStaleHistoryLoad()) {
          setError(i18n.t("chat.sessionUnavailable", "会话不存在或已被删除"));
        }
      } catch (err) {
        if (
          isStaleHistoryLoad() ||
          (err instanceof Error && err.name === "AbortError")
        ) {
          return null;
        }
        console.error("Failed to load session:", err);
        setError(i18n.t("chat.requestFailed"));
      } finally {
        if (historyAbortControllerRef.current === historyAbortController) {
          historyAbortControllerRef.current = null;
        }
        if (!isStaleHistoryLoad()) {
          setIsLoading(false);
          setIsLoadingHistory(false);
          isLoadingHistoryRef.current = false;
        }
      }

      return null;
    },
    [
      options,
      createSSEContext,
      canReadFeedback,
      clearSteerMessages,
      hydrateSteers,
      recordFirstWindow,
      recordFeedback,
      resetHistoryPagination,
    ],
  );

  // Send message
  const sendMessage = useCallback(
    async (
      content: string,
      agentOptions?: Record<string, boolean | string | number>,
      attachments?: MessageAttachment[],
      runOptions?: {
        enabledSkills?: string[];
        runModes?: Array<"auto" | "goal">;
      },
      submissionCallbacks?: ChatSubmissionCallbacks,
    ) => {
      if (!content.trim()) {
        notifySubmissionRejected(submissionCallbacks);
        return;
      }
      loadHistoryRequestIdRef.current += 1;
      historyAbortControllerRef.current?.abort();
      historyAbortControllerRef.current = null;

      const goalPlan = planGoalSubmission(content, goalModeEnabled);
      if (goalPlan.handledWithoutSend) {
        if (goalPlan.errorKey) {
          setError(i18n.t(goalPlan.errorKey, "Please enter a goal"));
          notifySubmissionRejected(submissionCallbacks);
          return;
        }
        setGoalModeEnabled(goalPlan.nextGoalModeEnabled);
        setActiveGoal(goalPlan.nextActiveGoal);
        setError(null);
        notifySubmissionAccepted(submissionCallbacks);
        return;
      }
      content = goalPlan.content;
      setGoalModeEnabled(goalPlan.nextGoalModeEnabled);
      setActiveGoal(goalPlan.nextActiveGoal);

      if (isSendingRef.current) {
        console.log(
          "[sendMessage] Already sending, ignoring duplicate request",
        );
        notifySubmissionRejected(submissionCallbacks);
        return;
      }
      isSendingRef.current = true;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      isConnectingRef.current = false;
      clearReconnectTimeout(reconnectTimeoutRef);

      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;

      const { messages: optimisticMessages, assistantMessageId } =
        createOptimisticMessagesForSend({
          previousMessages: messagesRef.current,
          content,
          attachments,
          enabledSkills: runOptions?.enabledSkills,
          runModes: runOptions?.runModes,
        });

      setMessages(optimisticMessages);
      setIsLoading(true);
      setError(null);
      let finalAssistantMessageId = assistantMessageId;
      let submissionAccepted = false;

      try {
        // 用户发送消息时标记当前 session 为已读
        if (sessionId) {
          sessionApi.markRead(sessionId).catch(() => {});
        }

        // 获取当前禁用的 skills 和 mcp_tools
        const personaPresetId = options?.getPersonaPresetId?.() || null;
        const disabledSkills = options?.getDisabledSkills?.() || [];
        const enabledSkills = resolveRunEnabledSkills({
          personaPresetId,
          personaEnabledSkills: options?.getEnabledSkills?.(),
          runEnabledSkills: runOptions?.enabledSkills,
        });
        const disabledMcpTools = options?.getDisabledMcpTools?.() || [];

        // Merge session-level agent options (e.g. model) with ChatInput values
        const fullAgentOptions = {
          ...options?.getAgentOptions?.(),
          ...agentOptions,
        };
        const requestTeamId = currentAgent === "team" ? selectedTeamId : null;
        const goalForRun = goalPlan.goal;

        // Prefetch/refresh access token in parallel with submit so SSE connect
        // rarely waits on a serial token refresh after POST returns.
        const [submitData] = await Promise.all([
          sessionApi.submitChat(
            currentAgent,
            content,
            sessionId ?? undefined,
            fullAgentOptions,
            attachments,
            pendingProjectIdRef.current ?? undefined,
            disabledSkills,
            disabledMcpTools,
            personaPresetId,
            enabledSkills,
            requestTeamId,
            goalForRun,
            runOptions?.runModes?.includes("auto") || undefined,
          ) as Promise<{
            session_id: string;
            run_id: string;
            trace_id: string;
            status: string;
            queue_position?: number;
          }>,
          getValidAccessToken().catch(() => null),
        ]);

        const newSessionId = submitData.session_id;
        const newRunId = submitData.run_id;
        const projectId = pendingProjectIdRef.current;
        submissionAccepted = true;
        notifySubmissionAccepted(submissionCallbacks);

        if (goalForRun) {
          const goalWithRunId = {
            ...goalForRun,
            runId: newRunId,
          };
          setActiveGoal((prev) =>
            prev
              ? {
                  ...prev,
                  runId: newRunId,
                }
              : goalWithRunId,
          );
          setGoalsByRunId((prev) => ({
            ...prev,
            [newRunId]: goalWithRunId,
          }));
        }

        // Clear pending project ID after use
        pendingProjectIdRef.current = null;

        // Handle queued status — show toast and wait via SSE
        if (submitData.status === "queued") {
          toast.loading(
            i18n.t("chat.queued", { position: submitData.queue_position }),
            { id: "chat-queue", duration: Infinity },
          );
          // 轮询刷新实时排队位置（自终止：出队/换轮次/网络错误即停）
          startQueuePositionPolling(newSessionId, newRunId);
        }

        if (!sessionId && newSessionId) {
          setSessionId(newSessionId);
          const now = new Date().toISOString();

          // 构建完整的对话配置
          const conversationConfig: Record<string, unknown> = {
            current_run_id: newRunId,
            agent_id: currentAgent,
            agent_options: fullAgentOptions,
            disabled_skills: disabledSkills,
            enabled_skills: enabledSkills,
            persona_preset_id: personaPresetId,
            disabled_mcp_tools: disabledMcpTools,
          };
          if (projectId) {
            conversationConfig.project_id = projectId;
          }
          if (currentAgent === "team" && selectedTeamId) {
            conversationConfig.team_id = selectedTeamId;
          }

          const newSession: BackendSession = {
            id: newSessionId,
            agent_id: currentAgent,
            created_at: now,
            updated_at: now,
            is_active: true,
            metadata: conversationConfig,
          };
          setNewlyCreatedSession(newSession);
          setCurrentProjectId(projectId);

          sessionApi
            .generateTitle(newSessionId, content, i18n.language)
            .then((result) => {
              setNewlyCreatedSession((prev) =>
                prev
                  ? {
                      ...prev,
                      name: result.title,
                      updated_at: new Date().toISOString(),
                    }
                  : null,
              );
              dispatchSessionTitleUpdated({
                sessionId: newSessionId,
                title: result.title,
              });
            })
            .catch((err) => {
              console.warn("[sendMessage] Failed to generate title:", err);
            });
        } else if (sessionId && newRunId) {
          // 更新现有 session 的 metadata
          const conversationConfig: Record<string, unknown> = {
            ...((newlyCreatedSession?.metadata as Record<string, unknown>) ||
              {}),
            current_run_id: newRunId,
            agent_id: currentAgent,
            agent_options: fullAgentOptions,
            disabled_skills: disabledSkills,
            enabled_skills: enabledSkills,
            persona_preset_id: personaPresetId,
            disabled_mcp_tools: disabledMcpTools,
          };
          if (currentAgent === "team" && selectedTeamId) {
            conversationConfig.team_id = selectedTeamId;
          }

          setNewlyCreatedSession((prev) =>
            prev
              ? {
                  ...prev,
                  metadata: conversationConfig,
                  updated_at: new Date().toISOString(),
                }
              : null,
          );
        }
        if (newRunId) {
          setCurrentRunId(newRunId);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? {
                    ...m,
                    id: newRunId,
                    runId: newRunId,
                  }
                : m,
            ),
          );
        }

        const streamSessionId = newSessionId || sessionId;
        const streamRunId = newRunId;
        finalAssistantMessageId = newRunId || assistantMessageId;

        if (!streamSessionId || !streamRunId) {
          throw new Error("Missing session_id or run_id");
        }

        isReconnectFromHistoryRef.current = false;
        const ctx = createSSEContext();
        await connectToSSE(
          streamSessionId,
          streamRunId,
          finalAssistantMessageId,
          ctx,
        );
      } catch (err) {
        if (!submissionAccepted) {
          notifySubmissionRejected(submissionCallbacks);
        }
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        const errWithMeta = err as Error & { code?: string };
        const errorMessage =
          err instanceof Error
            ? translateApiError(errWithMeta.code, err.message, undefined, i18n.t.bind(i18n))
            : i18n.t("chat.unknownError");
        setError(errorMessage);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === finalAssistantMessageId
              ? {
                  ...m,
                  content: i18n.t("chat.errorPrefix", { error: errorMessage }),
                  isStreaming: false,
                  parts: clearAllLoadingStates(m.parts || []),
                }
              : m,
          ),
        );
        setConnectionStatus("disconnected");
        setIsInitializingSandbox(false);
      } finally {
        setIsLoading(false);
        isSendingRef.current = false;
        const deferredSteers = deferredSteersRef.current.splice(0);
        if (deferredSteers.length > 0) {
          setTimeout(() => {
            for (const deferred of deferredSteers) {
              if (cancelledSteerIdsRef.current.has(deferred.id)) continue;
              clearSteer(deferred.content, deferred.id);
              sendMessageRef.current?.(deferred.content, deferred.attachments);
            }
          }, 0);
        }
      }
    },
    [
      sessionId,
      currentAgent,
      createSSEContext,
      newlyCreatedSession?.metadata,
      options,
      selectedTeamId,
      goalModeEnabled,
      clearSteer,
    ],
  );

  sendMessageRef.current = (
    content: string,
    attachments?: MessageAttachment[],
  ) => {
    return sendMessage(content, undefined, attachments);
  };

  // If the run finishes after the API accepted a steer but before the next
  // model boundary, promote it to a normal follow-up instead of leaving it
  // stranded above the composer.（运行中探测/重试在 hook 内部，见
  // useSteerFollowUpPromotion）
  useSteerFollowUpPromotion({
    isLoading,
    isSendingRef,
    steerMessages: steerQueue.steerMessages,
    clearSteer,
    cancelledSteerIdsRef,
    followUpSteerIdsRef,
    sessionIdRef,
    sendMessageRef,
  });

  const stopGeneration = useCallback(async () => {
    isSendingRef.current = false;
    setIsLoading(false);
    setIsInitializingSandbox(false);
    setSandboxError(null);

    // Clear approvals immediately (don't wait for SSE cancel event which may never arrive)
    options?.onClearApprovals?.(sessionIdRef.current ?? undefined);

    // Clear loading states on all messages and their parts
    setMessages((prev) =>
      prev.map((m) => ({
        ...m,
        isStreaming: false,
        parts: clearAllLoadingStates(m.parts || []),
      })),
    );

    const currentSessionId = sessionIdRef.current;
    if (currentSessionId) {
      try {
        await sessionApi.cancel(currentSessionId);
      } catch (error) {
        console.error(
          "[stopGeneration] Failed to call backend cancel API:",
          error,
        );
      }
    }
  }, [options]);

  const clearMessages = useCallback(() => {
    loadHistoryRequestIdRef.current += 1;
    streamVersionRef.current += 1;
    sseGenerationRef.current += 1;
    historyAbortControllerRef.current?.abort();
    historyAbortControllerRef.current = null;
    setMessages([]);
    clearSteerMessages();
    deferredSteersRef.current = [];
    setIsLoading(false);
    setIsLoadingHistory(false);
    isLoadingHistoryRef.current = false;
    isSendingRef.current = false;
    setSessionId(null);
    setError(null);
    setCurrentRunId(null);
    setConnectionStatus("disconnected");
    processedEventIdsRef.current.clear();
    lastHistoryTimestampRef.current = null;
    resetHistoryPagination();
    streamingMessageIdRef.current = null;
    sessionIdRef.current = null;
    currentRunIdRef.current = null;
    activeSubagentStackRef.current = [];
    setGoalModeEnabled(false);
    setActiveGoal(null);
    setGoalsByRunId({});
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    clearReconnectTimeout(reconnectTimeoutRef);
  }, [clearSteerMessages, resetHistoryPagination]);

  const clearActiveGoal = useCallback(() => {
    setGoalModeEnabled(false);
    setActiveGoal(null);
  }, []);

  const selectAgent = useCallback(
    (agentId: string) => {
      setCurrentAgent(agentId);
      clearMessages();
    },
    [clearMessages, setCurrentAgent],
  );

  // Switch agent without clearing messages (for mode toggling)
  const switchAgent = useCallback(
    (agentId: string) => {
      setCurrentAgent(agentId);
    },
    [setCurrentAgent],
  );

  // Select a team for team-mode agent
  const selectTeam = useCallback((teamId: string | null) => {
    setSelectedTeamId(teamId);
  }, []);

  const applyRecommendQuestions = useCallback(
    (runId: string, questions: string[]) => {
      setMessages((previous) =>
        applyRecommendQuestionsToMessages(previous, runId, questions),
      );
    },
    [],
  );

  // Reconnect function (managed by useSSEReconnect hook)
  const handleReconnectSSE = useSSEReconnect({
    createSSEContext,
    sessionIdRef,
    currentRunIdRef,
    isReconnectFromHistoryRef,
    streamingMessageIdRef,
    connectionStatus,
    setConnectionStatus,
  });

  return {
    messages,
    isLoading,
    isLoadingHistory,
    historyLoadGeneration,
    hasMoreHistoryTraces,
    isLoadingOlderHistory,
    error,
    sessionId,
    currentRunId,
    agents,
    currentAgent,
    agentsLoading,
    allowedModelIds,
    isReconnecting: connectionStatus === "reconnecting",
    connectionStatus,
    newlyCreatedSession,
    activeGoal,
    goalsByRunId,
    isInitializingSandbox,
    sandboxError,
    sendMessage,
    ...steerQueue,
    applyRecommendQuestions,
    clearActiveGoal,
    stopGeneration,
    clearMessages,
    selectAgent,
    switchAgent,
    selectTeam,
    selectedTeamId,
    goalModeEnabled,
    setGoalModeEnabled,
    autoModeEnabled,
    setAutoModeEnabled,
    refreshAgents: fetchAgents,
    loadHistory,
    loadOlderHistory,
    reconnectSSE: handleReconnectSSE,
    setPendingProjectId: (id: string | null) => {
      pendingProjectIdRef.current = id;
      autoExpandProjectIdRef.current = id;
    },
    autoExpandProjectId: autoExpandProjectIdRef.current,
    clearAutoExpandProjectId: (id?: string | null) => {
      if (
        id === undefined ||
        id === null ||
        autoExpandProjectIdRef.current === id
      ) {
        autoExpandProjectIdRef.current = null;
      }
    },
    currentProjectId,
  };
}

// Re-export types and utilities
export type {
  UseAgentOptions,
  UseAgentReturn,
  BackendSession,
} from "./useAgent/types";
