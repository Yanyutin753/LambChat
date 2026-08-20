/**
 * Main useAgent hook
 * Provides agent communication, message management, and SSE streaming
 */

import { useState, useCallback, useRef, useEffect } from "react";
import toast from "react-hot-toast";
import i18n from "../i18n";
import type {
  Message,
  AgentInfo,
  AgentListResponse,
  ConnectionStatus,
  MessageAttachment,
} from "../types";
import { sessionApi, type BackendSession } from "../services/api";
import { authenticatedRequest } from "../services/api/authenticatedRequest";
import { API_BASE } from "../services/api/config";
import { feedbackApi } from "../services/api/feedback";
import { useAuth } from "../hooks/useAuth";
import { Permission } from "../types/auth";
import {
  type UseAgentOptions,
  type SubagentStackItem,
  type HistoryEvent,
  type UseAgentReturn,
  type ActiveGoalSpec,
  type ChatSubmissionCallbacks,
} from "./useAgent/types";
import { applyRecommendQuestionsToMessages } from "./useAgent/recommendQuestionsUpdate";
import {
  reconstructMessagesFromEvents,
  getLastEventTimestamp,
  prepareMessagesForRunningRun,
  extractGoalFromEvents,
  extractGoalsByRunFromEvents,
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
import { useSteerQueue } from "./useAgent/steerQueue";
import { getValidAccessToken } from "../services/api/tokenManager";
import { resolveRunEnabledSkills } from "./useAgent/runSkillOverrides";
import { planGoalSubmission } from "./useAgent/goalCommands";
import { translateBackendError } from "../utils/backendErrors";
import { dispatchSessionTitleUpdated } from "../utils/sessionTitleEvents";
import { resolveAvailableAgentId } from "./useAgent/agentSelection";
import {
  applyFeedbackToMessages,
  resolveHistoryStreamRunId,
} from "./useAgent/historyLoadState";

function notifySubmissionAccepted(
  submissionCallbacks?: ChatSubmissionCallbacks,
): void {
  try {
    submissionCallbacks?.onAccepted();
  } catch (error) {
    console.error("Failed to clear accepted chat draft:", error);
  }
}

function notifySubmissionRejected(
  submissionCallbacks?: ChatSubmissionCallbacks,
): void {
  try {
    submissionCallbacks?.onRejected?.();
  } catch (error) {
    console.error("Failed to restore rejected chat draft:", error);
  }
}

export function useAgent(options?: UseAgentOptions): UseAgentReturn {
  const { hasAnyPermission } = useAuth();
  const canReadFeedback = hasAnyPermission([
    Permission.FEEDBACK_READ,
    Permission.FEEDBACK_WRITE,
  ]);

  // State
  const [messages, setMessages] = useState<Message[]>([]);

  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyLoadGeneration, setHistoryLoadGeneration] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [allowedModelIds, setAllowedModelIds] = useState<string[] | null>(null);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [newlyCreatedSession, setNewlyCreatedSession] =
    useState<BackendSession | null>(null);
  const [isInitializingSandbox, setIsInitializingSandbox] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [activeGoal, setActiveGoal] = useState<ActiveGoalSpec | null>(null);
  const [goalsByRunId, setGoalsByRunId] = useState<
    Record<string, ActiveGoalSpec>
  >({});
  const [goalModeEnabled, setGoalModeEnabled] = useState(false);
  const [autoModeEnabled, setAutoModeEnabled] = useState(() => {
    try {
      return localStorage.getItem("lamb-chat-auto-mode") === "true";
    } catch {
      return false;
    }
  });

  // Persist autoModeEnabled to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("lamb-chat-auto-mode", String(autoModeEnabled));
    } catch {
      /* storage unavailable */
    }
  }, [autoModeEnabled]);

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

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);
  const steerQueue = useSteerQueue({ sessionIdRef, setMessages, setError });

  useEffect(() => {
    currentRunIdRef.current = currentRunId;
  }, [currentRunId]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Create event handler context
  const createEventHandlerContext = useCallback(
    (): EventHandlerContext => ({
      options,
      sessionIdRef,
      processedEventIdsRef,
      lastHistoryTimestampRef,
      activeSubagentStackRef,
      streamVersionRef,
      setSessionId,
      setMessages,
      setConnectionStatus: (status) =>
        setConnectionStatus(status as ConnectionStatus),
      setIsInitializingSandbox,
      setSandboxError,
      setActiveGoal,
      setGoalsByRunId,
    }),
    [options],
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

  // Ref for currentAgent to avoid dependency changes triggering refetch
  const currentAgentRef = useRef(currentAgent);
  useEffect(() => {
    currentAgentRef.current = currentAgent;
  }, [currentAgent]);

  // Fetch available agents
  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const response = await authenticatedRequest(`${API_BASE}/api/agents`, {
        headers: {
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) throw new Error("Failed to fetch agents");
      const data: AgentListResponse = await response.json();
      const availableAgents = data.agents || [];
      setAgents(availableAgents);
      setAllowedModelIds(data.allowed_model_ids ?? null);
      const nextAgentId = resolveAvailableAgentId(
        currentAgentRef.current,
        data.default_agent,
        availableAgents,
      );
      if (nextAgentId !== currentAgentRef.current) {
        currentAgentRef.current = nextAgentId;
        setCurrentAgent(nextAgentId);
      }
    } catch (err) {
      console.error("Failed to fetch agents:", err);
    } finally {
      setAgentsLoading(false);
    }
  }, []); // No dependencies - uses ref instead

  // Load agents on mount
  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // Refresh agents when page becomes visible (e.g., switching back to /chat tab)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        fetchAgents();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [fetchAgents]);

  // Listen for agent preference updates to refresh agents list and apply new default
  useEffect(() => {
    const handleAgentPreferenceUpdated = async () => {
      // Fetch fresh agents data
      setAgentsLoading(true);
      try {
        const response = await authenticatedRequest(`${API_BASE}/api/agents`, {
          headers: {
            "Content-Type": "application/json",
          },
        });
        if (!response.ok) throw new Error("Failed to fetch agents");
        const data: AgentListResponse = await response.json();

        // Update agents list
        const availableAgents = data.agents || [];
        setAgents(availableAgents);
        setAllowedModelIds(data.allowed_model_ids ?? null);

        // Apply the new default agent if user doesn't have an active session
        // (i.e., no current messages means it's a good time to switch)
        const hasActiveSession = messagesRef.current.length > 0;
        const nextAgentId = resolveAvailableAgentId(
          hasActiveSession ? currentAgentRef.current : "",
          data.default_agent,
          availableAgents,
        );
        if (nextAgentId !== currentAgentRef.current) {
          currentAgentRef.current = nextAgentId;
          setCurrentAgent(nextAgentId);
        }
      } catch (err) {
        console.error("Failed to fetch agents after preference update:", err);
      } finally {
        setAgentsLoading(false);
      }
    };

    window.addEventListener(
      "agent-preference-updated",
      handleAgentPreferenceUpdated,
    );
    return () => {
      window.removeEventListener(
        "agent-preference-updated",
        handleAgentPreferenceUpdated,
      );
    };
  }, []);

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
      setError(null);

      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;
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
      options?.onClearApprovals?.();

      try {
        const [sessionData, eventsData] = await Promise.all([
          sessionApi.get(targetSessionId, { signal }),
          sessionApi.getEvents(targetSessionId, {
            include_active_user_message: true,
            compact_message_chunks: true,
            signal,
          }),
        ]);
        if (isStaleHistoryLoad()) return null;

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

          // 从 metadata 提取配置信息
          const sessionConfig = {
            agent_id: (sessionData.metadata?.agent_id as string) || undefined,
            agent_options:
              (sessionData.metadata?.agent_options as Record<
                string,
                boolean | string | number
              >) || undefined,
            disabled_tools:
              (sessionData.metadata?.disabled_tools as string[]) || undefined,
            disabled_skills:
              (sessionData.metadata?.disabled_skills as string[]) || undefined,
            enabled_skills:
              (sessionData.metadata?.enabled_skills as string[]) || undefined,
            persona_preset_id:
              (sessionData.metadata?.persona_preset_id as string) || undefined,
            persona_preset_name:
              (sessionData.metadata?.persona_preset_name as string) ||
              undefined,
            persona_snapshot:
              (sessionData.metadata?.persona_snapshot as
                | import("../types").PersonaPresetSnapshot
                | undefined) || undefined,
            disabled_mcp_tools:
              (sessionData.metadata?.disabled_mcp_tools as string[]) ||
              undefined,
            team_id: (sessionData.metadata?.team_id as string) || undefined,
          };
          setGoalModeEnabled(false);

          const historyEvents = (eventsData.events || []) as HistoryEvent[];
          let reconstructedMessages = reconstructMessagesFromEvents(
            historyEvents,
            processedEventIdsRef.current,
            { options, activeSubagentStack: activeSubagentStackRef.current },
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
    [options, createSSEContext, canReadFeedback],
  );

  // Send message
  const sendMessage = useCallback(
    async (
      content: string,
      agentOptions?: Record<string, boolean | string | number>,
      attachments?: MessageAttachment[],
      runOptions?: { enabledSkills?: string[] },
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
        const errorMessage =
          err instanceof Error
            ? translateBackendError(err.message, i18n.t.bind(i18n))
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
    ],
  );

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
  }, []);

  const clearActiveGoal = useCallback(() => {
    setGoalModeEnabled(false);
    setActiveGoal(null);
  }, []);

  const selectAgent = useCallback(
    (agentId: string) => {
      setCurrentAgent(agentId);
      clearMessages();
    },
    [clearMessages],
  );

  // Switch agent without clearing messages (for mode toggling)
  const switchAgent = useCallback((agentId: string) => {
    setCurrentAgent(agentId);
  }, []);

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
