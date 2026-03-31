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
import { feedbackApi } from "../services/api/feedback";
import { useAuth } from "../hooks/useAuth";
import { Permission } from "../types/auth";
import {
  API_BASE,
  type UseAgentOptions,
  type SubagentStackItem,
  type HistoryEvent,
  type UseAgentReturn,
} from "./useAgent/types";
import {
  reconstructMessagesFromEvents,
  getLastEventTimestamp,
} from "./useAgent/historyLoader";
import { clearAllLoadingStates } from "./useAgent/messageParts";
import { type EventHandlerContext } from "./useAgent/eventHandlers";
import {
  connectToSSE,
  reconnectSSE,
  clearReconnectTimeout,
  type SSEConnectionContext,
} from "./useAgent/sseConnection";

export function useAgent(options?: UseAgentOptions): UseAgentReturn {
  const { hasAnyPermission } = useAuth();
  const canReadFeedback = hasAnyPermission([
    Permission.FEEDBACK_READ,
    Permission.FEEDBACK_WRITE,
  ]);

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [newlyCreatedSession, setNewlyCreatedSession] =
    useState<BackendSession | null>(null);
  const [isInitializingSandbox, setIsInitializingSandbox] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);

  // Refs for connection management
  const abortControllerRef = useRef<AbortController | null>(null);
  const pendingProjectIdRef = useRef<string | null>(null);
  const autoExpandProjectIdRef = useRef<string | null>(null);
  const isConnectingRef = useRef(false);
  const isLoadingHistoryRef = useRef(false);
  const isSendingRef = useRef(false);
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
      setSessionId,
      setMessages,
      setConnectionStatus: (status) =>
        setConnectionStatus(status as ConnectionStatus),
      setIsInitializingSandbox,
      setSandboxError,
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

  // Fetch available agents
  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const response = await authenticatedRequest(`${API_BASE}/agents`, {
        headers: {
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) throw new Error("Failed to fetch agents");
      const data: AgentListResponse = await response.json();
      setAgents(data.agents || []);
      // Use ref to check currentAgent, avoiding dependency cycle
      if (!currentAgentRef.current && data.agents?.length > 0) {
        const defaultAgentId = data.default_agent || data.agents[0]?.id || "";
        if (defaultAgentId) {
          setCurrentAgent(defaultAgentId);
        }
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
        const response = await authenticatedRequest(`${API_BASE}/agents`, {
          headers: {
            "Content-Type": "application/json",
          },
        });
        if (!response.ok) throw new Error("Failed to fetch agents");
        const data: AgentListResponse = await response.json();

        // Update agents list
        setAgents(data.agents || []);

        // Apply the new default agent if user doesn't have an active session
        // (i.e., no current messages means it's a good time to switch)
        const hasActiveSession = messagesRef.current.length > 0;
        if (!hasActiveSession && data.default_agent) {
          setCurrentAgent(data.default_agent);
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
      if (isLoadingHistoryRef.current) {
        console.log(
          "[loadHistory] Switching to new session, aborting previous load...",
        );
      }
      isLoadingHistoryRef.current = true;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      isConnectingRef.current = false;
      streamingMessageIdRef.current = null;
      clearReconnectTimeout(reconnectTimeoutRef);

      setIsLoading(true);
      setError(null);

      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;

      // Clear existing messages and approvals before loading new session
      setMessages([]);
      setSessionId(null);
      options?.onClearApprovals?.();

      try {
        const sessionData = await sessionApi.get(targetSessionId);

        if (sessionData) {
          setSessionId(targetSessionId);
          setCurrentProjectId(
            (sessionData.metadata?.project_id as string) || null,
          );

          const currentRunId =
            targetRunId ||
            (sessionData.metadata?.current_run_id as string) ||
            null;

          // 并行发起 events、status 和 feedback 请求，减少串行等待时间
          const eventsPromise = sessionApi.getEvents(targetSessionId);
          const statusPromise = currentRunId
            ? sessionApi.getStatus(targetSessionId, currentRunId).catch((e) => {
                console.warn("[loadHistory] Failed to check status:", e);
                return null;
              })
            : Promise.resolve(null);
          const feedbackPromise = canReadFeedback
            ? feedbackApi
                .list(0, 100, undefined, undefined, targetSessionId)
                .catch((e) => {
                  console.warn("[loadHistory] Failed to load feedback:", e);
                  return null;
                })
            : Promise.resolve(null);

          const [eventsData, statusData, feedbackList] = await Promise.all([
            eventsPromise,
            statusPromise,
            feedbackPromise,
          ]);

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

            // Apply feedback (already loaded in parallel)
            if (feedbackList && feedbackList.items.length > 0) {
              const feedbackMap = new Map(
                feedbackList.items.map((f) => [
                  f.run_id,
                  { feedback: f.rating, feedbackId: f.id },
                ]),
              );
              reconstructedMessages = reconstructedMessages.map((msg) => {
                if (msg.runId) {
                  const feedbackInfo = feedbackMap.get(msg.runId);
                  if (feedbackInfo) {
                    return {
                      ...msg,
                      feedback: feedbackInfo.feedback,
                      feedbackId: feedbackInfo.feedbackId,
                    };
                  }
                }
                return msg;
              });
            }

            const lastTimestamp = getLastEventTimestamp(
              eventsData.events as HistoryEvent[],
            );
            if (lastTimestamp) {
              lastHistoryTimestampRef.current = lastTimestamp;
            }

            setMessages(reconstructedMessages);

            if (isTaskRunning && currentRunId) {
              setCurrentRunId(currentRunId);

              const streamingMessageId = crypto.randomUUID();
              const newAssistantMsg: Message = {
                id: streamingMessageId,
                role: "assistant",
                content: "",
                timestamp: new Date(),
                parts: [],
                isStreaming: true,
              };
              setMessages((prev) => [...prev, newAssistantMsg]);

              isReconnectFromHistoryRef.current = false;
              const ctx = createSSEContext();
              await connectToSSE(
                targetSessionId,
                currentRunId,
                streamingMessageId,
                ctx,
              );
            }
          } else {
            setMessages([]);

            if (isTaskRunning && currentRunId) {
              setCurrentRunId(currentRunId);
              isReconnectFromHistoryRef.current = false;

              const streamingMessageId = crypto.randomUUID();
              const newAssistantMsg: Message = {
                id: streamingMessageId,
                role: "assistant",
                content: "",
                timestamp: new Date(),
                parts: [],
                isStreaming: true,
              };
              setMessages([newAssistantMsg]);
              const ctx = createSSEContext();
              await connectToSSE(
                targetSessionId,
                currentRunId,
                streamingMessageId,
                ctx,
              );
            }
          }
        }
      } catch (err) {
        console.error("Failed to load session:", err);
        setError(i18n.t("chat.requestFailed"));
      } finally {
        setIsLoading(false);
        isLoadingHistoryRef.current = false;
      }
    },
    [options, createSSEContext, canReadFeedback],
  );

  // Send message
  const sendMessage = useCallback(
    async (
      content: string,
      agentOptions?: Record<string, boolean | string | number>,
      attachments?: MessageAttachment[],
    ) => {
      if (!content.trim()) return;

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

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: content.trim(),
        timestamp: new Date(),
        attachments: attachments,
      };

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        timestamp: new Date(),
        toolCalls: [],
        toolResults: [],
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsLoading(true);
      setError(null);

      try {
        const submitData = (await sessionApi.submitChat(
          currentAgent,
          content,
          sessionId ?? undefined,
          agentOptions,
          attachments,
          pendingProjectIdRef.current ?? undefined,
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
          const newSession: BackendSession = {
            id: newSessionId,
            agent_id: currentAgent,
            created_at: now,
            updated_at: now,
            is_active: true,
            metadata: projectId ? { project_id: projectId } : {},
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
            })
            .catch((err) => {
              console.warn("[sendMessage] Failed to generate title:", err);
            });
        }
        if (newRunId) {
          setCurrentRunId(newRunId);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessage.id ? { ...m, runId: newRunId } : m,
            ),
          );
        }

        const streamSessionId = newSessionId || sessionId;
        const streamRunId = newRunId;

        if (!streamSessionId || !streamRunId) {
          throw new Error("Missing session_id or run_id");
        }

        isReconnectFromHistoryRef.current = false;
        const ctx = createSSEContext();
        await connectToSSE(
          streamSessionId,
          streamRunId,
          assistantMessage.id,
          ctx,
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        const errorMessage =
          err instanceof Error ? err.message : i18n.t("chat.unknownError");
        setError(errorMessage);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessage.id
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
    [sessionId, currentAgent, createSSEContext],
  );

  const stopGeneration = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setConnectionStatus("disconnected");
    streamingMessageIdRef.current = null;
    isSendingRef.current = false;
    isConnectingRef.current = false;
    setIsLoading(false);
    setIsInitializingSandbox(false);
    setSandboxError(null);
    clearReconnectTimeout(reconnectTimeoutRef);
    activeSubagentStackRef.current = [];
    retryCountRef.current = 0;

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
    setMessages([]);
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
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    clearReconnectTimeout(reconnectTimeoutRef);
  }, []);

  const selectAgent = useCallback(
    (agentId: string) => {
      setCurrentAgent(agentId);
      clearMessages();
    },
    [clearMessages],
  );

  // Reconnect function
  const handleReconnectSSE = useCallback(async () => {
    const ctx = {
      ...createSSEContext(),
      sessionIdRef,
      currentRunIdRef,
      isReconnectFromHistoryRef,
    };
    await reconnectSSE(ctx);
  }, [createSSEContext]);

  // Handle visibility change
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (
        document.visibilityState === "visible" &&
        connectionStatus === "disconnected" &&
        sessionIdRef.current &&
        currentRunIdRef.current &&
        streamingMessageIdRef.current
      ) {
        handleReconnectSSE();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [connectionStatus, handleReconnectSSE]);

  // Handle network status changes
  useEffect(() => {
    const handleOnline = () => {
      if (
        connectionStatus === "disconnected" &&
        sessionIdRef.current &&
        currentRunIdRef.current &&
        streamingMessageIdRef.current
      ) {
        handleReconnectSSE();
      }
    };

    const handleOffline = () => {
      setConnectionStatus("disconnected");
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [connectionStatus, handleReconnectSSE]);

  return {
    messages,
    isLoading,
    error,
    sessionId,
    currentRunId,
    agents,
    currentAgent,
    agentsLoading,
    isReconnecting: connectionStatus === "reconnecting",
    connectionStatus,
    newlyCreatedSession,
    isInitializingSandbox,
    sandboxError,
    sendMessage,
    stopGeneration,
    clearMessages,
    selectAgent,
    refreshAgents: fetchAgents,
    loadHistory,
    reconnectSSE: handleReconnectSSE,
    setPendingProjectId: (id: string | null) => {
      pendingProjectIdRef.current = id;
      autoExpandProjectIdRef.current = id;
    },
    autoExpandProjectId: autoExpandProjectIdRef.current,
    currentProjectId,
  };
}

// Re-export types and utilities
export type {
  UseAgentOptions,
  UseAgentReturn,
  BackendSession,
} from "./useAgent/types";
export { API_BASE } from "./useAgent/types";
