/**
 * Main useAgent hook
 * Provides agent communication, message management, and SSE streaming
 */

import { useState, useCallback, useRef, useEffect } from "react";
import toast from "react-hot-toast";
import i18n from "../i18n";
import { resolveAgentDisplayName } from "../components/agent/agentCatalog";
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
  extractPersistentGoalFromEvents,
  createScheduledTaskApprovalLookup,
} from "./useAgent/historyLoader";
import { clearAllLoadingStates } from "./useAgent/messageParts";
import { type EventHandlerContext } from "./useAgent/eventHandlers";
import {
  connectToSSE,
  clearReconnectTimeout,
  type SSEConnectionContext,
} from "./useAgent/sseConnection";
import { useStreamReconcile } from "./useAgent/sseReconcile";
import { createOptimisticMessagesForSend } from "./useAgent/optimisticMessages";
import { startQueuePositionPolling } from "./useAgent/queuePolling";
import {
  useSteerQueue,
  useSteerFollowUpPromotion,
} from "./useAgent/steerQueue";
import { getValidAccessToken } from "../services/api/tokenManager";
import { resolveRunEnabledSkills } from "./useAgent/runSkillOverrides";
import {
  parseFrontendGoalCommand,
  planGoalSubmission,
} from "./useAgent/goalCommands";
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
import { getGoalControlScope } from "./useAgent/goalControlScope";
import { selectPersistentGoal } from "./useAgent/persistentGoalState";
import { usePersistentGoalRuntime } from "./useAgent/persistentGoalRuntime";
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
    isLoading,
    setIsLoading,
    isLoadingHistory,
    setIsLoadingHistory,
    historyLoadGeneration,
    setHistoryLoadGeneration,
    sessionId,
    setSessionId,
    currentProjectId,
    setCurrentProjectId,
    error,
    setError,
    connectionStatus,
    setConnectionStatus,
    currentRunId,
    setCurrentRunId,
    newlyCreatedSession,
    setNewlyCreatedSession,
    isInitializingSandbox,
    setIsInitializingSandbox,
    sandboxError,
    setSandboxError,
    selectedTeamId,
    setSelectedTeamId,
    persistentGoal,
    setPersistentGoal: setPersistentGoalState,
    persistentGoalBusy,
    setPersistentGoalBusy,
    activeGoal,
    setActiveGoal,
    goalsByRunId,
    setGoalsByRunId,
    goalModeEnabled,
    setGoalModeEnabled,
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
  // 发送所有权序号：fetch-event-source 的 abort 是 resolve 而非 reject，
  // 被顶掉的旧 sendMessage 的 finally 必然执行且不得重置共享标志
  const sendSeqRef = useRef(0);
  // submitChat POST 在途（服务端尚未受理）：此窗口内打断补充会造成同会话双提交
  const submitInFlightRef = useRef(false);
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

  // 最近一次流事件（含 ping）时刻：回前台对账/看门狗的存活信号
  const lastStreamActivityAtRef = useRef<number | null>(null);

  // 最新 loadHistory 的稳定引用：SSE 层发现「run 已终结但本地空壳」时
  // 拉起历史重载（定义在下方，渲染期回填，避免 useCallback 依赖环）
  const loadHistoryRef = useRef<
    ((targetSessionId: string, targetRunId?: string) => Promise<unknown>) | null
  >(null);

  // Flag for reconnect from history
  const isReconnectFromHistoryRef = useRef<boolean>(false);

  // Stream version to invalidate stale SSE events after clearMessages
  const streamVersionRef = useRef(0);

  // Keep sessionId/runId in ref for closure access
  const sessionIdRef = useRef<string | null>(null);
  const currentRunIdRef = useRef<string | null>(null);
  const messagesRef = useRef<Message[]>([]);
  const historyMessagesSnapshotRef = useRef<{
    requestId: number;
    sourceSessionId: string | null;
    targetSessionId: string;
    messages: Message[];
  } | null>(null);
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
  const {
    markSteerDelivered,
    clearSteerMessages,
    clearSteer,
    hydrateSteers,
    queueFollowUp,
    restoreSteerMessages,
    bindSteerSession,
  } = steerQueue;

  useEffect(() => {
    currentRunIdRef.current = currentRunId;
  }, [currentRunId]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const {
    setPersistentGoal,
    persistentMutationRef,
    persistentMutationEpochRef,
    controlPersistentGoal,
  } = usePersistentGoalRuntime({
    sessionId,
    persistentGoal,
    setPersistentGoalState,
    setPersistentGoalBusy,
    setError,
    sessionIdRef,
    currentRunIdRef,
    isSendingRef,
    isLoadingHistoryRef,
    loadHistoryRef,
  });

  // 历史回放查到已决的 scheduled-task 审批时，补收尾对应 ask_human pill（详见 historyLoader）
  // eslint-disable-next-line react-hooks/exhaustive-deps -- 工厂仅依赖 useState 的稳定 setter
  const onApprovalLookup = useCallback(
    createScheduledTaskApprovalLookup(setMessages),
    [],
  );

  // History trace-window pagination (older pages prepend on scroll)
  const {
    hasMoreHistoryTraces,
    isLoadingOlderHistory,
    recordFirstWindow,
    createHistoryReplayContext,
    recordOptimisticUser,
    recordFeedback,
    loadOlderHistory,
    loadTargetHistory,
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
    loadHistoryRequestIdRef,
    historyAbortControllerRef,
    setIsLoadingHistory,
    setError,
  });

  // Create event handler context
  const createEventHandlerContext = useCallback(
    (historyRunId?: string): EventHandlerContext => ({
      ...createHistoryReplayContext(
        historyRunId || currentRunIdRef.current || undefined,
      ),
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
      setPersistentGoal,
      setGoalsByRunId,
      onStaleRunStateDetected: (runId: string) => {
        // 已提交的旧流可能尚未退出；只阻止新 POST/历史加载，避免漏补完整回答。
        const activeSessionId = sessionIdRef.current;
        if (
          activeSessionId &&
          currentRunIdRef.current === runId &&
          !submitInFlightRef.current &&
          !isLoadingHistoryRef.current
        ) {
          void loadHistoryRef.current?.(activeSessionId);
        }
      },
    }),
    [
      options,
      createHistoryReplayContext,
      markSteerDelivered,
      setCurrentRunId,
      setSessionId,
      setMessages,
      setConnectionStatus,
      setIsInitializingSandbox,
      setSandboxError,
      setActiveGoal,
      setPersistentGoal,
      setGoalsByRunId,
    ],
  );

  // Create SSE connection context
  const createSSEContext = useCallback(
    (historyRunId?: string): SSEConnectionContext => ({
      ...createEventHandlerContext(historyRunId),
      abortControllerRef,
      sseGenerationRef,
      isConnectingRef,
      streamingMessageIdRef,
      reconnectTimeoutRef,
      retryCountRef,
      messagesRef,
      lastStreamActivityAtRef,
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
    agentsError,
    allowedModelIds,
    fetchAgents,
  } = useAgentList(hasActiveMessages);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      sendSeqRef.current += 1;
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
      const supersedesSameSessionLoad =
        sessionIdRef.current === targetSessionId && isLoadingHistoryRef.current;
      if (
        targetRunId &&
        sessionIdRef.current === targetSessionId &&
        !supersedesSameSessionLoad
      ) {
        return loadTargetHistory(targetSessionId, targetRunId);
      }
      const previousSnapshot = historyMessagesSnapshotRef.current;
      const snapshotMessages =
        messagesRef.current.length === 0 &&
        previousSnapshot?.requestId === loadHistoryRequestIdRef.current &&
        previousSnapshot.sourceSessionId === sessionIdRef.current
          ? previousSnapshot.messages
          : messagesRef.current;
      sendSeqRef.current += 1;
      submitInFlightRef.current = false;
      isSendingRef.current = false;
      if (sessionIdRef.current !== targetSessionId) setPersistentGoal(null);
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
      // Only a send taking over this same-session refresh may restore its snapshot.
      historyMessagesSnapshotRef.current = {
        requestId,
        sourceSessionId: sessionIdRef.current,
        targetSessionId,
        messages: snapshotMessages,
      };
      setMessages([]);
      // Clear the previous view; restore this session's local follow-ups after access is verified.
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
        const pendingSteersPromise = sessionApi
          .getPendingSteers(targetSessionId, { signal })
          .catch((error) => {
            console.warn(
              "[loadHistory] Failed to restore pending steers:",
              error,
            );
            return { session_id: targetSessionId, items: [] };
          });
        const persistentGoalPromise = sessionApi
          .getPersistentGoal(targetSessionId, { signal })
          .catch(() => undefined);
        const [sessionData, eventsData] = await Promise.all([
          sessionApi.get(targetSessionId, { signal }),
          sessionApi.getEvents(targetSessionId, {
            include_active_user_message: true,
            compact_message_chunks: true,
            include_approval_statuses: true,
            // 首屏只取最近一页轮次，更早的在向上滚动时按游标分页加载
            trace_limit: HISTORY_TRACE_PAGE_SIZE,
            signal,
          }),
        ]);
        if (isStaleHistoryLoad()) {
          return null;
        }

        if (
          targetRunId &&
          !eventsData.events.some((event) => event.run_id === targetRunId)
        ) {
          const targetData = await sessionApi.getEvents(targetSessionId, {
            run_id: targetRunId,
            include_active_user_message: true,
            compact_message_chunks: true,
            include_approval_statuses: true,
            signal,
          });
          if (isStaleHistoryLoad()) return null;
          eventsData.events = [...targetData.events, ...eventsData.events];
          eventsData.approval_statuses = {
            ...eventsData.approval_statuses,
            ...targetData.approval_statuses,
          };
        }

        if (sessionData) {
          restoreSteerMessages(targetSessionId);
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
            (supersedesSameSessionLoad &&
              (sessionData.metadata?.current_run_id as string)) ||
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
              approvalStatuses: eventsData.approval_statuses,
              isCurrent: () => !isStaleHistoryLoad(),
              onApprovalLookup,
            },
          );
          const lastTimestamp = getLastEventTimestamp(historyEvents);
          lastHistoryTimestampRef.current = lastTimestamp;

          const restoredGoal = extractGoalFromEvents(historyEvents);
          const restoredGoalsByRun = extractGoalsByRunFromEvents(historyEvents);
          const streamRunId = resolveHistoryStreamRunId(
            eventsData.stream_run_id,
            supersedesSameSessionLoad ? undefined : targetRunId,
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

          if (isStaleHistoryLoad()) {
            return null;
          }
          setCurrentRunId(currentRunId);
          setActiveGoal(restoredGoal);
          setGoalsByRunId(restoredGoalsByRun);
          setMessages(reconstructedMessages);
          if (historyMessagesSnapshotRef.current?.requestId === requestId) {
            historyMessagesSnapshotRef.current = null;
          }

          // Show full primary history before optional reads; keep hydration before SSE.
          const pendingSteersData = await pendingSteersPromise;
          if (isStaleHistoryLoad()) return null;
          hydrateSteers(pendingSteersData.items);
          const persistentSnapshot = await persistentGoalPromise;
          if (isStaleHistoryLoad()) return null;
          setPersistentGoal((previous) =>
            selectPersistentGoal(
              previous,
              persistentSnapshot
                ? persistentSnapshot.goal
                : extractPersistentGoalFromEvents(
                    historyEvents,
                    targetSessionId,
                  ),
              targetSessionId,
            ),
          );

          void feedbackPromise.then((feedbackList) => {
            if (!feedbackList || isStaleHistoryLoad()) return;
            recordFeedback(feedbackList.items);
            setMessages((previous) =>
              applyFeedbackToMessages(previous, feedbackList.items),
            );
          });

          if (streamRunId && streamingMessageId) {
            isReconnectFromHistoryRef.current = false;
            const ctx = createSSEContext(streamRunId);
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
        if (historyMessagesSnapshotRef.current?.requestId === requestId) {
          historyMessagesSnapshotRef.current = null;
        }
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
      restoreSteerMessages,
      recordFirstWindow,
      loadTargetHistory,
      recordFeedback,
      resetHistoryPagination,
      onApprovalLookup,
      setActiveGoal,
      setPersistentGoal,
      setCurrentProjectId,
      setCurrentRunId,
      setError,
      setGoalModeEnabled,
      setGoalsByRunId,
      setHistoryLoadGeneration,
      setIsLoading,
      setIsLoadingHistory,
      setSessionId,
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
      const historySnapshot = historyMessagesSnapshotRef.current;
      historyMessagesSnapshotRef.current = null;
      if (
        historySnapshot?.requestId === loadHistoryRequestIdRef.current &&
        historySnapshot.sourceSessionId === sessionIdRef.current &&
        historySnapshot.targetSessionId === sessionIdRef.current &&
        messagesRef.current.length === 0
      ) {
        messagesRef.current = historySnapshot.messages;
        setMessages(historySnapshot.messages);
      }
      // 顶掉在途 loadHistory：同步释放其加载标志，否则该加载被 stale 后
      // 无人复位，isLoadingHistory 会永久卡死
      loadHistoryRequestIdRef.current += 1;
      historyAbortControllerRef.current?.abort();
      historyAbortControllerRef.current = null;
      setIsLoadingHistory(false);
      isLoadingHistoryRef.current = false;

      const command = parseFrontendGoalCommand(content);
      if (
        command &&
        (command.action === "persist" ||
          command.action === "pause" ||
          command.action === "resume" ||
          (command.action === "clear" &&
            getGoalControlScope(activeGoal, persistentGoal) === "persistent"))
      ) {
        if (attachments?.length) {
          setError(i18n.t("chat.goalPersistent.attachmentsUnsupported"));
          notifySubmissionRejected(submissionCallbacks);
          return;
        }
        if (persistentMutationRef.current || submitInFlightRef.current) {
          notifySubmissionRejected(submissionCallbacks);
          return;
        }
        persistentMutationRef.current = true;
        persistentMutationEpochRef.current += 1;
        setPersistentGoalBusy(true);
        const originSession = sessionIdRef.current;
        const originStreamVersion = streamVersionRef.current;
        let target = originSession;
        try {
          if (command.action !== "persist" && !target)
            throw new Error(i18n.t("chat.goalPersistent.noGoal"));
          if (!target) {
            const created = await sessionApi.create({
              name:
                command.action === "persist"
                  ? command.goal.objective
                  : undefined,
              metadata: {
                agent_id: currentAgent,
                agent_options: {
                  ...options?.getAgentOptions?.(),
                  ...agentOptions,
                },
                team_id: currentAgent === "team" ? selectedTeamId : null,
                persona_preset_id: options?.getPersonaPresetId?.() || null,
                disabled_skills: options?.getDisabledSkills?.() || [],
                enabled_skills: resolveRunEnabledSkills({
                  personaPresetId: options?.getPersonaPresetId?.() || null,
                  personaEnabledSkills: options?.getEnabledSkills?.(),
                  runEnabledSkills: runOptions?.enabledSkills,
                }),
                disabled_mcp_tools: options?.getDisabledMcpTools?.() || [],
                project_id: pendingProjectIdRef.current,
              },
            });
            if (
              sessionIdRef.current !== originSession ||
              streamVersionRef.current !== originStreamVersion
            ) {
              notifySubmissionRejected(submissionCallbacks);
              return;
            }
            target = created.id;
            sessionIdRef.current = target;
            setSessionId(target);
            setNewlyCreatedSession(created);
            setCurrentProjectId(pendingProjectIdRef.current);
            bindSteerSession(target);
          }
          const response =
            command.action === "persist"
              ? await sessionApi.putPersistentGoal(target, {
                  objective: command.goal.objective,
                  rubric: command.goal.rubric!,
                  ...(persistentGoal
                    ? { expected_revision: persistentGoal.revision }
                    : {}),
                })
              : await sessionApi.controlPersistentGoal(target, command.action);
          if (
            sessionIdRef.current !== target ||
            streamVersionRef.current !== originStreamVersion
          ) {
            notifySubmissionRejected(submissionCallbacks);
            return;
          }
          if (command.action === "persist" && !response.goal)
            throw new Error(i18n.t("chat.goalPersistent.noGoal"));
          if (response.goal && response.goal.session_id !== target)
            throw new Error(i18n.t("chat.goalPersistent.noGoal"));
          setPersistentGoal((previous) =>
            selectPersistentGoal(previous, response.goal, target),
          );
          setGoalModeEnabled(false);
          setError(null);
          notifySubmissionAccepted(submissionCallbacks);
        } catch (error) {
          const apiError = error as Error & {
            code?: string;
            args?: Record<string, unknown>;
          };
          if (
            sessionIdRef.current === target &&
            streamVersionRef.current === originStreamVersion
          )
            setError(
              translateApiError(
                apiError.code,
                apiError.message,
                apiError.args,
                i18n.t,
              ),
            );
          notifySubmissionRejected(submissionCallbacks);
        } finally {
          persistentMutationRef.current = false;
          setPersistentGoalBusy(false);
        }
        return;
      }
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
      // 发送所有权：后续发送/停止会递增序号夺走所有权，旧发送的 finally
      // 据此让位，不再触碰 isLoading/isSendingRef（abort=resolve 必走 finally）
      const sendSeq = ++sendSeqRef.current;
      const ownsSend = () => sendSeqRef.current === sendSeq;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      isConnectingRef.current = false;
      clearReconnectTimeout(reconnectTimeoutRef);

      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;

      const personaSnapshot =
        currentAgent === "team" ? null : options?.getPersonaSnapshot?.();
      const selectedAgent = agents.find((agent) => agent.id === currentAgent);
      const { messages: optimisticMessages, assistantMessageId } =
        createOptimisticMessagesForSend({
          previousMessages: messagesRef.current,
          assistantIdentity: {
            seed: personaSnapshot?.preset_id || currentAgent,
            name:
              personaSnapshot?.name ||
              (selectedAgent
                ? resolveAgentDisplayName(selectedAgent, i18n.language, i18n.t)
                : `agents.${currentAgent}.name`),
            avatar: personaSnapshot
              ? personaSnapshot.avatar || null
              : selectedAgent?.icon || null,
          },
          content,
          attachments,
          enabledSkills: runOptions?.enabledSkills,
          runModes: runOptions?.runModes,
        });

      setMessages(optimisticMessages);
      setCurrentRunId(null);
      setIsLoading(true);
      setError(null);
      let finalAssistantMessageId = assistantMessageId;
      let submissionAccepted = false;
      let sendStreamGeneration: number | null = null;

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
        submitInFlightRef.current = true;
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
        submissionAccepted = true;
        notifySubmissionAccepted(submissionCallbacks);
        // Leaving the view does not cancel an accepted server task. Its late
        // admission must not attach an SSE stream or mutate the next chat.
        if (!ownsSend()) return;
        const projectId = pendingProjectIdRef.current;
        submitInFlightRef.current = false;

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
          bindSteerSession(newSessionId);
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
        recordOptimisticUser(
          streamRunId,
          optimisticMessages[optimisticMessages.length - 2],
        );
        const ctx = createSSEContext(streamRunId);
        const streamPromise = connectToSSE(
          streamSessionId,
          streamRunId,
          finalAssistantMessageId,
          ctx,
        );
        sendStreamGeneration = sseGenerationRef.current;
        await streamPromise;
      } catch (err) {
        if (!submissionAccepted) {
          notifySubmissionRejected(submissionCallbacks);
        }
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        // 被后续发送/停止顶掉的旧发送不渲染错误（当前发送 owns 标志）
        if (!ownsSend()) return;
        const errWithMeta = err as Error & { code?: string };
        const errorMessage =
          err instanceof Error
            ? translateApiError(
                errWithMeta.code,
                err.message,
                undefined,
                i18n.t.bind(i18n),
              )
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
        // 收尾自己的乐观助手气泡：流被后续发送/停止顶掉时不会再收到
        // 终态事件，不落定会留下永久 isStreaming 的空气泡
        setMessages((prev) => {
          // 前台重连接管同一气泡后，旧发送退出不得封存新流。
          if (
            sendStreamGeneration !== null &&
            sendStreamGeneration !== sseGenerationRef.current &&
            streamingMessageIdRef.current === finalAssistantMessageId
          ) {
            return prev;
          }
          const target = prev.find(
            (m) => m.id === finalAssistantMessageId && m.isStreaming,
          );
          if (!target) return prev;
          return prev.map((m) =>
            m.id === finalAssistantMessageId
              ? {
                  ...m,
                  isStreaming: false,
                  parts: clearAllLoadingStates(m.parts || []),
                }
              : m,
          );
        });
        // 仅当前所有者重置共享标志；finally 里不能 return（会吞异常）
        if (ownsSend()) {
          submitInFlightRef.current = false;
          setIsLoading(false);
          isSendingRef.current = false;
          const deferredSteers = deferredSteersRef.current.splice(0);
          if (deferredSteers.length > 0) {
            setTimeout(() => {
              for (const deferred of deferredSteers) {
                if (cancelledSteerIdsRef.current.has(deferred.id)) continue;
                clearSteer(deferred.content, deferred.id);
                sendMessageRef.current?.(
                  deferred.content,
                  deferred.attachments,
                );
              }
            }, 0);
          }
        }
      }
    },
    [
      sessionId,
      currentAgent,
      createSSEContext,
      recordOptimisticUser,
      newlyCreatedSession?.metadata,
      agents,
      setIsLoadingHistory,
      options,
      selectedTeamId,
      goalModeEnabled,
      persistentGoal,
      persistentMutationEpochRef,
      persistentMutationRef,
      activeGoal,
      setPersistentGoal,
      setPersistentGoalBusy,
      clearSteer,
      bindSteerSession,
      setActiveGoal,
      setConnectionStatus,
      setCurrentProjectId,
      setCurrentRunId,
      setError,
      setGoalModeEnabled,
      setGoalsByRunId,
      setIsInitializingSandbox,
      setIsLoading,
      setNewlyCreatedSession,
      setSessionId,
    ],
  );

  sendMessageRef.current = (
    content: string,
    attachments?: MessageAttachment[],
  ) => {
    return sendMessage(content, undefined, attachments);
  };

  // SSE 层 onStaleRunStateDetected 回调经此拿到最新 loadHistory
  loadHistoryRef.current = loadHistory;

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
    // 用户停止即夺取发送所有权：在途 sendMessage 的 finally 不得再重置
    // 共享标志（否则会把停止后新发送刚置好的状态抹掉）
    sendSeqRef.current += 1;
    submitInFlightRef.current = false;
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
  }, [options, setIsInitializingSandbox, setIsLoading, setSandboxError]);

  // 补充当前问题：打断进行中的 run，把补充内容并入这轮思考重新生成
  // （原问题与已生成部分保留在历史，新一轮自动携带完整上下文）
  const supplementFollowUp = useCallback(
    async (content: string, attachments?: MessageAttachment[]) => {
      const text = content.trim();
      if (!text && !attachments?.length) return;
      // isSendingRef 在整个流式期间恒为 true，不能用它在途判定；只有
      // POST 尚未被服务端受理时打断才会造成同会话双提交——仅该窗口转排队
      if (submitInFlightRef.current) {
        queueFollowUp(text, attachments);
        return;
      }
      await stopGeneration();
      await sendMessageRef.current?.(text, attachments);
    },
    [queueFollowUp, stopGeneration],
  );

  const clearMessages = useCallback(() => {
    sendSeqRef.current += 1;
    submitInFlightRef.current = false;
    pendingProjectIdRef.current = null;
    setCurrentProjectId(null);
    loadHistoryRequestIdRef.current += 1;
    historyMessagesSnapshotRef.current = null;
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
    setPersistentGoal(null);
    setGoalsByRunId({});
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    clearReconnectTimeout(reconnectTimeoutRef);
  }, [
    clearSteerMessages,
    resetHistoryPagination,
    setActiveGoal,
    setPersistentGoal,
    setConnectionStatus,
    setCurrentRunId,
    setCurrentProjectId,
    setError,
    setGoalModeEnabled,
    setGoalsByRunId,
    setIsLoading,
    setIsLoadingHistory,
    setSessionId,
  ]);

  const clearActiveGoal = useCallback(() => {
    setGoalModeEnabled(false);
    setActiveGoal(null);
  }, [setActiveGoal, setGoalModeEnabled]);

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
  const selectTeam = useCallback(
    (teamId: string | null) => {
      setSelectedTeamId(teamId);
    },
    [setSelectedTeamId],
  );

  const applyRecommendQuestions = useCallback(
    (runId: string, questions: string[]) => {
      setMessages((previous) =>
        applyRecommendQuestionsToMessages(previous, runId, questions),
      );
    },
    [],
  );

  // Reconcile function (managed by useStreamReconcile hook):
  // 回前台/网络恢复/静默看门狗对流对账；带 runId 时退化为原重连语义
  const reconcileActiveRun = useStreamReconcile({
    createSSEContext,
    sessionIdRef,
    currentRunIdRef,
    isReconnectFromHistoryRef,
    streamingMessageIdRef,
    connectionStatus,
    setConnectionStatus,
    isSendingRef,
    isLoadingHistoryRef,
    loadHistoryRef,
  });

  return {
    messages,
    isLoading,
    canContinueInBackground: Boolean(
      isLoading &&
        sessionId &&
        currentRunId &&
        !isLoadingHistory &&
        !submitInFlightRef.current,
    ),
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
    agentsError,
    allowedModelIds,
    isReconnecting: connectionStatus === "reconnecting",
    connectionStatus,
    newlyCreatedSession,
    activeGoal,
    persistentGoal,
    persistentGoalBusy,
    controlPersistentGoal,
    goalsByRunId,
    isInitializingSandbox,
    sandboxError,
    sendMessage,
    ...steerQueue,
    supplementFollowUp,
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
    reconnectSSE: reconcileActiveRun,
    reconcileActiveRun,
    setPendingProjectId: (id: string | null) => {
      pendingProjectIdRef.current = id;
      autoExpandProjectIdRef.current = id;
      setCurrentProjectId(id);
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
