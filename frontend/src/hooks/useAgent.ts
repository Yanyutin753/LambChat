/**
 * Main useAgent hook
 * Provides agent communication, message management, and SSE streaming
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import toast from "react-hot-toast";
import i18n from "../i18n";
import { uuid } from "../utils/uuid";
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
import { useAuth } from "../hooks/useAuth";
import { Permission } from "../types/auth";
import { hydrateMessageActionHistory } from "../components/chat/ChatMessage/messageActionHistoryHydrators";
import {
  type UseAgentOptions,
  type SubagentStackItem,
  type HistoryEvent,
  type UseAgentReturn,
  type ActiveGoalSpec,
  type SendMessageOptions,
} from "./useAgent/types";
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
import {
  createOptimisticMessagesForRetry,
  createOptimisticMessagesForSend,
} from "./useAgent/optimisticMessages";
import { resolveRunEnabledSkills } from "./useAgent/runSkillOverrides";
import {
  planGoalSubmission,
  type GoalSubmissionPlan,
} from "./useAgent/goalCommands";
import { translateBackendError } from "../utils/backendErrors";
import { dispatchSessionTitleUpdated } from "../utils/sessionTitleEvents";
import { resolveAvailableAgentId } from "./useAgent/agentSelection";
import {
  importLegacyPayloadPluginOptions,
  legacyPayloadKeysForPluginOption,
  pluginOptionsFromMetadata,
  retainPluginOptionsForDeclarations,
  selectedAgentTeamIdFromMetadata,
  withPluginOption,
  type PluginOptionsMetadata,
} from "../extensions/pluginOptions";
import {
  buildSessionOptionContributions,
  buildMessageActionContributions,
  hasAgentCatalogEntryContribution,
} from "../extensions/coreContributions";

export function useAgent(options?: UseAgentOptions): UseAgentReturn {
  const { hasAnyPermission } = useAuth();
  const canReadFeedback = hasAnyPermission([
    Permission.FEEDBACK_READ,
    Permission.FEEDBACK_WRITE,
  ]);
  const messageActionHistoryContributions = useMemo(
    () =>
      canReadFeedback
        ? buildMessageActionContributions(options?.runtimePlugins, {
            target: "assistant_message",
          })
        : [],
    [canReadFeedback, options?.runtimePlugins],
  );

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
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
  const [legacyTeamId, setLegacyTeamId] = useState<string | null>(null);
  const [sessionPluginOptions, setSessionPluginOptions] =
    useState<PluginOptionsMetadata>({});
  const selectedTeamId = selectedAgentTeamIdFromMetadata({
    plugin_options: sessionPluginOptions,
    team_id: legacyTeamId ?? undefined,
  });
  const [activeGoal, setActiveGoal] = useState<ActiveGoalSpec | null>(null);
  const [goalsByRunId, setGoalsByRunId] = useState<
    Record<string, ActiveGoalSpec>
  >({});
  const [goalModeEnabled, setGoalModeEnabled] = useState(false);

  // Refs for connection management
  const abortControllerRef = useRef<AbortController | null>(null);
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

  const isCurrentAgentAvailable = useCallback(
    (agentId: string) => agents.some((agent) => agent.id === agentId),
    [agents],
  );

  const currentSessionOptionContributions = useMemo(
    () =>
      isCurrentAgentAvailable(currentAgent)
        ? buildSessionOptionContributions(options?.runtimePlugins, {
            agentId: currentAgent,
          })
        : [],
    [currentAgent, isCurrentAgentAvailable, options?.runtimePlugins],
  );

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
      const isStaleHistoryLoad = () =>
        requestId !== loadHistoryRequestIdRef.current;

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
      const markReadPromise = sessionApi
        .markRead(targetSessionId)
        .catch(() => {});

      // Clear approvals before loading new session
      options?.onClearApprovals?.();

      try {
        await markReadPromise;
        if (isStaleHistoryLoad()) return null;

        const sessionData = await sessionApi.get(targetSessionId);
        if (isStaleHistoryLoad()) return null;

        if (sessionData) {
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
            plugin_options:
              (sessionData.metadata?.plugin_options as
                | Record<string, Record<string, unknown>>
                | undefined) || undefined,
          };
          setSessionPluginOptions(
            pluginOptionsFromMetadata({
              plugin_options: sessionConfig.plugin_options,
            }),
          );
          setLegacyTeamId(
            typeof sessionConfig.team_id === "string" && sessionConfig.team_id.trim()
              ? sessionConfig.team_id
              : null,
          );
          setGoalModeEnabled(false);

          // 并行发起 events、status 和 feedback 请求，减少串行等待时间
          const eventsPromise = sessionApi.getEvents(targetSessionId);
          const statusPromise = currentRunId
            ? sessionApi.getStatus(targetSessionId, currentRunId).catch((e) => {
                console.warn("[loadHistory] Failed to check status:", e);
                return null;
              })
            : Promise.resolve(null);
          const [eventsData, statusData] = await Promise.all([
            eventsPromise,
            statusPromise,
          ]);
          if (isStaleHistoryLoad()) return null;

          let isTaskRunning = false;
          if (statusData) {
            isTaskRunning =
              statusData.status === "pending" ||
              statusData.status === "running";
          }

          if (eventsData.events && eventsData.events.length > 0) {
            let reconstructedMessages = reconstructMessagesFromEvents(
              eventsData.events as HistoryEvent[],
              processedEventIdsRef.current,
              { options, activeSubagentStack: activeSubagentStackRef.current },
            );

            reconstructedMessages = await hydrateMessageActionHistory(
              messageActionHistoryContributions,
              {
                sessionId: targetSessionId,
                messages: reconstructedMessages,
              },
            ).catch((e) => {
              console.warn("[loadHistory] Failed to hydrate message actions:", e);
              return reconstructedMessages;
            });

            const lastTimestamp = getLastEventTimestamp(
              eventsData.events as HistoryEvent[],
            );
            if (lastTimestamp) {
              lastHistoryTimestampRef.current = lastTimestamp;
            }
            if (isStaleHistoryLoad()) return null;

            // Reconstruct active goal from history events (goal:start / goal:end)
            const restoredGoal = extractGoalFromEvents(
              eventsData.events as HistoryEvent[],
            );
            if (isStaleHistoryLoad()) return null;
            setActiveGoal(restoredGoal);
            setGoalsByRunId(
              extractGoalsByRunFromEvents(eventsData.events as HistoryEvent[]),
            );

            // When the task is still running, target the assistant message for
            // that same run. If history has the user message but no assistant
            // events yet, append a fresh assistant bubble after the latest user.
            if (isTaskRunning && currentRunId) {
              setCurrentRunId(currentRunId);

              const prepared = prepareMessagesForRunningRun(
                reconstructedMessages,
                currentRunId,
                undefined,
                messagesRef.current,
              );
              reconstructedMessages = prepared.messages;
              const streamingMessageId = prepared.streamingMessageId;

              setMessages(reconstructedMessages);

              // Fire-and-forget SSE reconnect so that loadHistory
              // returns sessionConfig immediately, allowing the caller
              // (useSessionSync) to restore model selection and other UI
              // state without being blocked by the long-lived connection.
              isReconnectFromHistoryRef.current = false;
              const ctx = createSSEContext();
              connectToSSE(
                targetSessionId,
                currentRunId,
                streamingMessageId,
                ctx,
              ).catch((e) => {
                console.warn("[loadHistory] SSE reconnect failed:", e);
              });
            } else {
              setMessages(reconstructedMessages);
            }
          } else {
            setMessages([]);
            setActiveGoal(null);
            setGoalsByRunId({});

            if (isTaskRunning && currentRunId) {
              setCurrentRunId(currentRunId);
              isReconnectFromHistoryRef.current = false;

              const streamingMessageId = uuid();
              const prepared = prepareMessagesForRunningRun(
                [],
                currentRunId,
                () => streamingMessageId,
                messagesRef.current,
              );
              setMessages(prepared.messages);
              // Fire-and-forget SSE reconnect (same reason as above).
              const ctx = createSSEContext();
              connectToSSE(
                targetSessionId,
                currentRunId,
                streamingMessageId,
                ctx,
              ).catch((e) => {
                console.warn("[loadHistory] SSE reconnect failed:", e);
              });
            }
          }

          // Return sessionConfig *before* any SSE reconnect so that the
          // caller can immediately restore model selection / agent / config.

          return sessionConfig;
        }
      } catch (err) {
        if (isStaleHistoryLoad()) return null;
        console.error("Failed to load session:", err);
        setError(i18n.t("chat.requestFailed"));
      } finally {
        if (!isStaleHistoryLoad()) {
          setIsLoading(false);
          setIsLoadingHistory(false);
          isLoadingHistoryRef.current = false;
        }
      }

      return null;
    },
    [options, createSSEContext, messageActionHistoryContributions],
  );

  // Send message
  const sendMessage = useCallback(
    async (
      content: string,
      agentOptions?: Record<string, boolean | string | number>,
      attachments?: MessageAttachment[],
      sendOptions?: SendMessageOptions,
    ) => {
      if (!content.trim()) return;
      loadHistoryRequestIdRef.current += 1;

      const retryUserMessage = sendOptions?.retryUserMessage === true;
      if (retryUserMessage && !sessionId) {
        setError(i18n.t("chat.requestFailed"));
        return;
      }

      const goalPlan: GoalSubmissionPlan = retryUserMessage
        ? {
            content,
            goal: null,
            nextGoalModeEnabled: goalModeEnabled,
            nextActiveGoal: activeGoal,
            handledWithoutSend: false,
          }
        : planGoalSubmission(content, goalModeEnabled);
      if (goalPlan.handledWithoutSend) {
        if (goalPlan.errorKey) {
          setError(i18n.t(goalPlan.errorKey, "Please enter a goal"));
          return;
        }
        setGoalModeEnabled(goalPlan.nextGoalModeEnabled);
        setActiveGoal(goalPlan.nextActiveGoal);
        setError(null);
        return;
      }
      content = goalPlan.content;
      setGoalModeEnabled(goalPlan.nextGoalModeEnabled);
      setActiveGoal(goalPlan.nextActiveGoal);

      if (isSendingRef.current) {
        console.log(
          "[sendMessage] Already sending, ignoring duplicate request",
        );
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
        retryUserMessage
          ? createOptimisticMessagesForRetry({
              previousMessages: messagesRef.current,
              assistantMessageId: sendOptions?.retryAssistantMessageId,
              afterUserMessageId: sendOptions?.retryAfterUserMessageId,
            })
          : createOptimisticMessagesForSend({
              previousMessages: messagesRef.current,
              content,
              attachments,
            });

      setMessages(optimisticMessages);
      setIsLoading(true);
      setError(null);
      let finalAssistantMessageId = assistantMessageId;

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
          runEnabledSkills: sendOptions?.enabledSkills,
        });
        const disabledMcpTools = options?.getDisabledMcpTools?.() || [];

        // Merge session-level agent options (e.g. model) with ChatInput values
        const fullAgentOptions = {
          ...options?.getAgentOptions?.(),
          ...agentOptions,
        };
        const sessionOptionSeed = importLegacyPayloadPluginOptions(
          {
            plugin_options: sessionPluginOptions,
            team_id: legacyTeamId ?? undefined,
          },
          currentSessionOptionContributions,
          sessionPluginOptions,
        );
        const requestPluginOptions = retainPluginOptionsForDeclarations(
          sessionOptionSeed,
          currentSessionOptionContributions,
        );
        const canUseLegacyTeamField =
          selectedTeamId &&
          isCurrentAgentAvailable(currentAgent) &&
          hasAgentCatalogEntryContribution(currentAgent, options?.runtimePlugins);
        const requestTeamId = canUseLegacyTeamField && Object.keys(requestPluginOptions).length === 0
          ? selectedTeamId
          : null;
        const goalForRun = goalPlan.goal;

        const submitData = (await sessionApi.submitChat(
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
          requestPluginOptions,
          goalForRun,
          { retryUserMessage },
        )) as {
          session_id: string;
          run_id: string;
          trace_id: string;
          status: string;
          queue_position?: number;
        };

        const newSessionId = submitData.session_id;
        const newRunId = submitData.run_id;
        const projectId = pendingProjectIdRef.current;

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
          if (Object.keys(requestPluginOptions).length > 0) {
            conversationConfig.plugin_options = requestPluginOptions;
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
          if (Object.keys(requestPluginOptions).length > 0) {
            conversationConfig.plugin_options = requestPluginOptions;
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
      currentSessionOptionContributions,
      isCurrentAgentAvailable,
      legacyTeamId,
      newlyCreatedSession?.metadata,
      options,
      selectedTeamId,
      sessionPluginOptions,
      goalModeEnabled,
      activeGoal,
    ],
  );

  const stopGeneration = useCallback(async () => {
    isSendingRef.current = false;
    setIsLoading(false);
    setIsInitializingSandbox(false);
    setSandboxError(null);

    // Clear approvals immediately (don't wait for SSE cancel event which may never arrive)
    options?.onClearApprovals?.();

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
    setLegacyTeamId(null);
    setSessionPluginOptions({});
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
  const setSessionPluginOption = useCallback(
    (pluginId: string, key: string, value: unknown) => {
      setSessionPluginOptions((current) => {
        const next = withPluginOption(
          { plugin_options: current },
          pluginId,
          key,
          value,
        ).plugin_options;
        return next ?? {};
      });
      if (
        currentSessionOptionContributions.some((option) => {
          return (
            option.pluginId === pluginId &&
            option.key === key &&
            legacyPayloadKeysForPluginOption(option).includes("team_id")
          );
        })
      ) {
        setLegacyTeamId(null);
      }
    },
    [currentSessionOptionContributions],
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
    clearActiveGoal,
    stopGeneration,
    clearMessages,
    selectAgent,
    switchAgent,
    selectedTeamId,
    sessionPluginOptions,
    setSessionPluginOption,
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
  SendMessageOptions,
} from "./useAgent/types";
