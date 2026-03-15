/**
 * Main useAgent hook
 * Provides agent communication, message management, and SSE streaming
 */

import { useState, useCallback, useRef, useEffect } from "react";
import i18n from "../i18n";
import type {
  Message,
  AgentInfo,
  AgentListResponse,
  ConnectionStatus,
  MessageAttachment,
} from "../types";
import {
  sessionApi,
  getAccessToken,
  type BackendSession,
} from "../services/api";
import { feedbackApi } from "../services/api/feedback";
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
  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
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
      const token = getAccessToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
      const response = await fetch(`${API_BASE}/agents`, { headers });
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
        const token = getAccessToken();
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE}/agents`, { headers });
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

      // Clear existing messages before loading new session
      setMessages([]);
      setSessionId(null);

      try {
        const sessionData = await sessionApi.get(targetSessionId);

        if (sessionData) {
          setSessionId(targetSessionId);

          const currentRunId =
            targetRunId ||
            (sessionData.metadata?.current_run_id as string) ||
            null;

          let isTaskRunning = false;
          if (currentRunId) {
            try {
              const statusData = await sessionApi.getStatus(
                targetSessionId,
                currentRunId,
              );
              isTaskRunning =
                statusData.status === "pending" ||
                statusData.status === "running";
            } catch (statusErr) {
              console.warn("[loadHistory] Failed to check status:", statusErr);
            }
          }

          const eventsData = await sessionApi.getEvents(targetSessionId);

          if (eventsData.events && eventsData.events.length > 0) {
            let reconstructedMessages = reconstructMessagesFromEvents(
              eventsData.events as HistoryEvent[],
              processedEventIdsRef.current,
              { options, activeSubagentStack: activeSubagentStackRef.current },
            );

            // Load feedback for this session
            try {
              const feedbackList = await feedbackApi.list(
                0,
                100,
                undefined,
                undefined,
                targetSessionId,
              );
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
            } catch (feedbackErr) {
              console.warn(
                "[loadHistory] Failed to load feedback:",
                feedbackErr,
              );
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
        setError("Failed to load session");
      } finally {
        setIsLoading(false);
        isLoadingHistoryRef.current = false;
      }
    },
    [options, createSSEContext],
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
        const token = getAccessToken();
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const disabledTools = options?.getEnabledTools?.();
        const submitResponse = await fetch(
          `${API_BASE}/chat/stream?agent_id=${currentAgent}`,
          {
            method: "POST",
            headers,
            body: JSON.stringify({
              message: content,
              session_id: sessionId,
              disabled_tools: disabledTools,
              agent_options: agentOptions,
              attachments: attachments?.map((a) => ({
                id: a.id,
                key: a.key,
                name: a.name,
                type: a.type,
                mime_type: a.mimeType,
                size: a.size,
                url: a.url,
              })),
            }),
          },
        );

        if (!submitResponse.ok) {
          throw new Error(`Submit failed: ${submitResponse.status}`);
        }

        const submitData = await submitResponse.json();
        const newSessionId = submitData.session_id;
        const newRunId = submitData.run_id;

        if (!sessionId && newSessionId) {
          setSessionId(newSessionId);
          const now = new Date().toISOString();
          const newSession: BackendSession = {
            id: newSessionId,
            agent_id: currentAgent,
            created_at: now,
            updated_at: now,
            is_active: true,
            metadata: {},
          };
          setNewlyCreatedSession(newSession);

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
          err instanceof Error ? err.message : "Unknown error";
        setError(errorMessage);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessage.id
              ? {
                  ...m,
                  content: `Error: ${errorMessage}`,
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
    [sessionId, currentAgent, options, createSSEContext],
  );

  const stopGeneration = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setConnectionStatus("disconnected");
    streamingMessageIdRef.current = null;
    isSendingRef.current = false;
    setIsLoading(false);
    setIsInitializingSandbox(false);

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
  }, []);

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
  };
}

// Re-export types and utilities
export type {
  UseAgentOptions,
  UseAgentReturn,
  BackendSession,
} from "./useAgent/types";
export { API_BASE } from "./useAgent/types";
