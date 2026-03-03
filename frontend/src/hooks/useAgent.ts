import { useState, useCallback, useRef, useEffect } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  Message,
  ToolCall,
  ToolResult,
  AgentInfo,
  AgentListResponse,
  ConnectionStatus,
  ThinkingPart,
  MessagePart,
  SandboxPart,
  TokenUsagePart,
  MessageAttachment,
} from "../types";
import {
  sessionApi,
  getAccessToken,
  type BackendSession,
} from "../services/api";
import {
  API_BASE,
  DEFAULT_AGENT,
  type EventType,
  type StreamEvent,
  type EventData,
  type UseAgentOptions,
  type SubagentStackItem,
  type HistoryEvent,
} from "./useAgent/types";
import {
  addPartToDepth,
  updateSubagentResult,
  updateToolResultInDepth,
  createToolPart,
  createThinkingPart,
  createSubagentPart,
} from "./useAgent/messageParts";
import {
  convertAttachments,
  reconstructMessagesFromEvents,
  getLastEventTimestamp,
} from "./useAgent/historyLoader";

export function useAgent(options?: UseAgentOptions) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgent, setCurrentAgent] = useState<string>(DEFAULT_AGENT);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [newlyCreatedSession, setNewlyCreatedSession] =
    useState<BackendSession | null>(null);

  // Sandbox initialization state
  const [isInitializingSandbox, setIsInitializingSandbox] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);

  // Refs for connection management
  const abortControllerRef = useRef<AbortController | null>(null);
  const isConnectingRef = useRef(false);
  const isLoadingHistoryRef = useRef(false);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const retryCountRef = useRef(0);

  // Track processed event IDs to prevent duplicates
  const processedEventIdsRef = useRef<Set<string>>(new Set());

  // Track last event timestamp from history to prevent duplicates when reconnecting
  const lastHistoryTimestampRef = useRef<Date | null>(null);

  // Subagent tracking stack for parallel subagent support
  const activeSubagentStackRef = useRef<SubagentStackItem[]>([]);

  // Current streaming message ID
  const streamingMessageIdRef = useRef<string | null>(null);

  // Flag for reconnect from history
  const isReconnectFromHistoryRef = useRef<boolean>(false);

  // Keep sessionId in ref for closure access
  const sessionIdRef = useRef<string | null>(null);
  const currentRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    currentRunIdRef.current = currentRunId;
  }, [currentRunId]);

  // Clear reconnect timeout
  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  // Fetch available agents
  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agents`);
      if (!response.ok) throw new Error("Failed to fetch agents");
      const data: AgentListResponse = await response.json();
      setAgents(data.agents || []);
    } catch (err) {
      console.error("Failed to fetch agents:", err);
    } finally {
      setAgentsLoading(false);
    }
  }, []);

  // Load agents on mount
  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      clearReconnectTimeout();
    };
  }, [clearReconnectTimeout]);

  // Handle incoming SSE events
  const handleStreamEvent = useCallback(
    (
      event: StreamEvent,
      messageId: string,
      eventId: string,
      eventTimestamp?: string,
    ) => {
      console.log("[handleStreamEvent] Received event:", {
        eventType: event.event,
        messageId,
        eventId,
      });

      // Skip if already processed by ID
      if (processedEventIdsRef.current.has(eventId)) {
        console.log("[SSE] Skipping duplicate event by ID:", eventId);
        return;
      }

      // Skip if this event is older than the last history timestamp
      if (eventTimestamp && lastHistoryTimestampRef.current) {
        const eventTime = new Date(eventTimestamp);
        const historyTime = lastHistoryTimestampRef.current;
        if (eventTime < historyTime) {
          console.log(
            "[SSE] Skipping duplicate event by timestamp:",
            eventId,
            eventTime.toISOString(),
            "<",
            historyTime.toISOString(),
          );
          return;
        }
      }

      processedEventIdsRef.current.add(eventId);

      const eventType = event.event;
      let data: EventData = {};
      try {
        data = JSON.parse(event.data);
      } catch {
        // Fallback for non-JSON data
      }

      const depth = data.depth || 0;

      switch (eventType) {
        case "metadata": {
          if (data.session_id && !sessionIdRef.current) {
            setSessionId(data.session_id);
          }
          break;
        }

        case "user:message": {
          const userContent = data.content || "";
          const userAttachments = convertAttachments(data.attachments);

          if (userContent) {
            setMessages((prev) => {
              if (prev.length === 0) {
                const newUserMessage: Message = {
                  id: crypto.randomUUID(),
                  role: "user",
                  content: userContent,
                  timestamp: eventTimestamp
                    ? new Date(eventTimestamp)
                    : new Date(),
                  attachments: userAttachments,
                };
                return [...prev, newUserMessage];
              }
              const existingUserMsg = prev.find(
                (m) => m.role === "user" && m.content === userContent,
              );
              if (existingUserMsg) return prev;

              const newUserMessage: Message = {
                id: crypto.randomUUID(),
                role: "user",
                content: userContent,
                timestamp: eventTimestamp
                  ? new Date(eventTimestamp)
                  : new Date(),
                attachments: userAttachments,
              };
              const streamingAssistantIndex = prev.findIndex(
                (m) => m.role === "assistant" && m.isStreaming,
              );
              if (streamingAssistantIndex !== -1) {
                const newMessages = [...prev];
                newMessages.splice(streamingAssistantIndex, 0, newUserMessage);
                return newMessages;
              }
              return [...prev, newUserMessage];
            });
          }
          break;
        }

        case "agent:call": {
          const agentId = data.agent_id || "unknown";
          const subagentPart = createSubagentPart(
            agentId,
            data.agent_name || data.agent_id || "Unknown Agent",
            data.input || "",
            depth,
          );

          activeSubagentStackRef.current.push({
            agent_id: agentId,
            depth: depth,
            message_id: messageId,
          });

          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              const newParts = addPartToDepth(
                parts,
                subagentPart,
                depth,
                activeSubagentStackRef.current,
                agentId,
                messageId,
              );
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "agent:result": {
          const agentId = data.agent_id || "unknown";
          const stackIndex = activeSubagentStackRef.current.findIndex(
            (item) =>
              item.agent_id === agentId && item.message_id === messageId,
          );
          if (stackIndex !== -1) {
            activeSubagentStackRef.current.splice(stackIndex, 1);
          }

          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              const newParts = updateSubagentResult(
                parts,
                agentId,
                data.result || "",
                data.success !== false,
                depth,
              );
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "thinking": {
          const content = data.content || "";
          const thinkingId = data.thinking_id;
          if (content) {
            const thinkingPart = createThinkingPart(
              content,
              thinkingId,
              depth,
              data.agent_id,
              true,
            );
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== messageId) return m;
                const parts = m.parts || [];
                if (depth > 0) {
                  const newParts = addPartToDepth(
                    parts,
                    thinkingPart,
                    depth,
                    activeSubagentStackRef.current,
                    data.agent_id as string,
                    messageId,
                  );
                  return { ...m, parts: newParts };
                } else {
                  const newParts = [...parts];
                  let existingIndex = -1;

                  // 如果有 thinking_id，精确匹配
                  if (thinkingId !== undefined) {
                    existingIndex = newParts.findIndex(
                      (p) =>
                        p.type === "thinking" && p.thinking_id === thinkingId,
                    );
                  } else {
                    // 如果没有 thinking_id，找最后一个 thinking part（且也没有 thinking_id）
                    for (let i = newParts.length - 1; i >= 0; i--) {
                      const p = newParts[i];
                      if (
                        p.type === "thinking" &&
                        p.thinking_id === undefined
                      ) {
                        existingIndex = i;
                        break;
                      }
                    }
                  }

                  if (existingIndex >= 0) {
                    const existing = newParts[existingIndex] as ThinkingPart;
                    newParts[existingIndex] = {
                      ...existing,
                      content: existing.content + content,
                      isStreaming: true,
                    };
                  } else {
                    newParts.push(thinkingPart);
                  }
                  return { ...m, parts: newParts };
                }
              }),
            );
          }
          break;
        }

        case "message:chunk": {
          const content = data.content || "";
          if (content) {
            setMessages((prev) => {
              const targetMessage = prev.find((m) => m.id === messageId);
              if (!targetMessage) return prev;

              return prev.map((m) => {
                if (m.id !== messageId) return m;
                const parts = m.parts || [];

                if (depth > 0) {
                  const textPart = {
                    type: "text" as const,
                    content,
                    depth,
                    agent_id: data.agent_id,
                  };
                  const newParts = addPartToDepth(
                    parts,
                    textPart,
                    depth,
                    activeSubagentStackRef.current,
                    data.agent_id as string,
                    messageId,
                  );
                  return { ...m, parts: newParts };
                } else {
                  const newParts = [...parts];
                  const lastPart = newParts[newParts.length - 1];
                  if (lastPart?.type === "text" && !lastPart.depth) {
                    newParts[newParts.length - 1] = {
                      ...lastPart,
                      content: lastPart.content + content,
                    };
                  } else {
                    newParts.push({ type: "text" as const, content });
                  }
                  return {
                    ...m,
                    content: m.content + content,
                    parts: newParts,
                  };
                }
              });
            });
          }
          break;
        }

        case "tool:start": {
          const toolCallId = data.tool_call_id as string | undefined;
          const toolCall: ToolCall = {
            id: toolCallId,
            name: data.tool || "",
            args: data.args || {},
          };
          const toolPart = createToolPart(
            data.tool || "",
            data.args || {},
            depth,
            data.agent_id as string | undefined,
            toolCallId,
          );
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              let newParts: MessagePart[];

              if (depth > 0) {
                newParts = addPartToDepth(
                  parts,
                  toolPart,
                  depth,
                  activeSubagentStackRef.current,
                  data.agent_id as string,
                  messageId,
                );
              } else {
                newParts = [...parts, toolPart];
              }
              return {
                ...m,
                toolCalls:
                  depth === 0
                    ? [...(m.toolCalls || []), toolCall]
                    : m.toolCalls,
                parts: newParts,
              };
            }),
          );
          break;
        }

        case "tool:result": {
          const toolCallId = data.tool_call_id as string | undefined;
          const isSuccess =
            data.success !== false &&
            !data.result?.toString().startsWith("Error:");
          const toolResult: ToolResult = {
            id: toolCallId,
            name: data.tool || "",
            result: data.result || "",
            success: isSuccess,
          };
          const errorMsg = data.error as string | undefined;
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];

              if (depth > 0 || toolCallId) {
                // 优先使用 tool_call_id 匹配
                const newParts = updateToolResultInDepth(
                  parts,
                  toolCallId || "",
                  toolResult.result,
                  toolResult.success,
                  errorMsg,
                  depth,
                  data.agent_id as string,
                );
                return { ...m, parts: newParts };
              } else {
                // 向后兼容：按 name 匹配
                const toolName = data.tool || "";
                let updated = false;
                const newParts = parts.map((p) => {
                  if (
                    p.type === "tool" &&
                    p.name === toolName &&
                    p.isPending &&
                    !updated
                  ) {
                    updated = true;
                    return {
                      ...p,
                      result: toolResult.result,
                      success: toolResult.success,
                      error: errorMsg,
                      isPending: false,
                    };
                  }
                  return p;
                });
                return {
                  ...m,
                  toolResults: [...(m.toolResults || []), toolResult],
                  parts: newParts,
                };
              }
            }),
          );
          break;
        }

        case "done": {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === messageId ? { ...m, isStreaming: false } : m,
            ),
          );
          setConnectionStatus("disconnected");
          streamingMessageIdRef.current = null;
          break;
        }

        case "error": {
          const errorMsg = data.error || "Unknown error";
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              return {
                ...m,
                content: `Error: ${errorMsg}`,
                isStreaming: false,
              };
            }),
          );
          setConnectionStatus("disconnected");
          streamingMessageIdRef.current = null;
          options?.onClearApprovals?.();
          break;
        }

        case "approval_required": {
          if (data.id && options?.onApprovalRequired) {
            fetch(`/human/${data.id}`)
              .then((response) => (response.ok ? response.json() : null))
              .then((approval) => {
                if (approval && approval.status === "pending") {
                  options?.onApprovalRequired?.({
                    id: data.id!,
                    message: approval.message || "",
                    type: approval.type || "form",
                    fields: approval.fields || [],
                  });
                }
              })
              .catch((err) => {
                console.warn("[SSE] Failed to check approval status:", err);
              });
          }
          break;
        }

        case "sandbox:starting": {
          setIsInitializingSandbox(true);
          setSandboxError(null);
          const startingPart: SandboxPart = {
            type: "sandbox",
            status: "starting",
            timestamp: data.timestamp,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? startingPart : p))
                : [...parts, startingPart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "sandbox:state": {
          const statePart: SandboxPart = {
            type: "sandbox",
            status: data.state as "starting" | "ready" | "error",
            timestamp: data.timestamp,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? statePart : p))
                : [...parts, statePart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "sandbox:ready": {
          setIsInitializingSandbox(false);
          const readyPart: SandboxPart = {
            type: "sandbox",
            status: "ready",
            sandbox_id: data.sandbox_id,
            work_dir: data.work_dir,
            timestamp: data.timestamp,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? readyPart : p))
                : [...parts, readyPart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "sandbox:error": {
          setIsInitializingSandbox(false);
          setSandboxError(data.error || "沙箱初始化失败");
          const errorPart: SandboxPart = {
            type: "sandbox",
            status: "error",
            error: data.error,
            timestamp: data.timestamp,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? errorPart : p))
                : [...parts, errorPart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "token:usage": {
          const tokenUsage: TokenUsagePart = {
            type: "token_usage",
            input_tokens: data.input_tokens || 0,
            output_tokens: data.output_tokens || 0,
            total_tokens: data.total_tokens || 0,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              return {
                ...m,
                tokenUsage,
                duration: data.duration ? data.duration * 1000 : undefined,
              };
            }),
          );
          break;
        }

        case "skill:added": {
          const skillName = data.name || "";
          const skillDescription = data.description || "";
          const filesCount = data.files_count || 0;
          console.log("[SSE] Skill added:", skillName, "files:", filesCount);

          // 调用回调通知外部刷新 skills
          if (options?.onSkillAdded) {
            options.onSkillAdded(skillName, skillDescription, filesCount);
          }
          break;
        }
      }
    },
    [options],
  );

  // Connect to SSE stream
  const connectToSSE = useCallback(
    async (targetSessionId: string, targetRunId: string, messageId: string) => {
      if (isConnectingRef.current) {
        console.log("[SSE] Connection already in progress, skipping...");
        return;
      }
      isConnectingRef.current = true;
      streamingMessageIdRef.current = messageId;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      const token = getAccessToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      console.log(
        `[SSE] Connecting: session=${targetSessionId}, run_id=${targetRunId}`,
      );

      setConnectionStatus("connecting");
      retryCountRef.current = 0;

      try {
        await fetchEventSource(
          `${API_BASE}/chat/sessions/${targetSessionId}/stream?run_id=${targetRunId}`,
          {
            headers,
            signal: abortControllerRef.current.signal,
            openWhenHidden: true,
            onopen: async (response) => {
              if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
              }
              console.log("[SSE] Connection established");
              setConnectionStatus("connected");
              retryCountRef.current = 0;
            },
            onmessage: (event) => {
              if (event.event === "ping") return;
              const eventId = event.id || crypto.randomUUID();
              try {
                const parsedData = JSON.parse(event.data);
                const timestamp = parsedData._timestamp as string | undefined;
                const streamEvent: StreamEvent = {
                  event: event.event as EventType,
                  data: event.data,
                };
                handleStreamEvent(streamEvent, messageId, eventId, timestamp);
              } catch {
                // Ignore parse errors
              }
            },
            onerror: (err) => {
              console.error("[SSE] Connection error:", err);
              setConnectionStatus("reconnecting");
            },
            onclose: () => {
              console.log("[SSE] Connection closed");
              setConnectionStatus("disconnected");
              isConnectingRef.current = false;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === messageId ? { ...m, isStreaming: false } : m,
                ),
              );
            },
          },
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          console.log("[SSE] Connection aborted");
          return;
        }
        console.error("[SSE] Connection error:", err);
        setConnectionStatus("disconnected");
      } finally {
        isConnectingRef.current = false;
      }
    },
    [handleStreamEvent],
  );

  // Exponential backoff for reconnection
  const getReconnectDelay = useCallback((retryCount: number): number => {
    const baseDelay = Math.min(Math.pow(2, retryCount), 30) * 1000;
    const jitter = Math.random() * 1000;
    return baseDelay + jitter;
  }, []);

  // Smart reconnect with exponential backoff
  const reconnectSSE = useCallback(async () => {
    const currentSessId = sessionIdRef.current;
    const currentRId = currentRunIdRef.current;
    const currentMsgId = streamingMessageIdRef.current;

    if (!currentSessId || !currentRId) {
      console.log("[SSE] No session/run ID, skipping reconnect");
      return;
    }

    clearReconnectTimeout();

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    isConnectingRef.current = false;

    try {
      const statusData = await sessionApi.getStatus(currentSessId, currentRId);
      if (statusData.status === "completed" || statusData.status === "error") {
        console.log("[SSE] Task already completed");
        setConnectionStatus("disconnected");
        streamingMessageIdRef.current = null;
        return;
      }
    } catch (err) {
      console.error("[SSE] Failed to check task status:", err);
    }

    setConnectionStatus("reconnecting");

    const delay = getReconnectDelay(retryCountRef.current);
    retryCountRef.current += 1;
    console.log(
      `[SSE] Scheduling reconnect in ${delay}ms (retry ${retryCountRef.current})`,
    );

    reconnectTimeoutRef.current = setTimeout(async () => {
      if (currentMsgId) {
        const msgs = messages;
        const lastMsg = msgs.find((m) => m.id === currentMsgId);
        if (lastMsg) {
          isReconnectFromHistoryRef.current = true;
          await connectToSSE(currentSessId, currentRId, currentMsgId);
        }
      }
    }, delay);
  }, [clearReconnectTimeout, getReconnectDelay, connectToSSE, messages]);

  // Load message history from backend
  const loadHistory = useCallback(
    async (targetSessionId: string, targetRunId?: string) => {
      // Allow switching sessions anytime - abort previous loading
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
      clearReconnectTimeout();

      setIsLoading(true);
      setError(null);

      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;

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
            const reconstructedMessages = reconstructMessagesFromEvents(
              eventsData.events as HistoryEvent[],
              processedEventIdsRef.current,
              { options, activeSubagentStack: activeSubagentStackRef.current },
            );

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
              await connectToSSE(
                targetSessionId,
                currentRunId,
                streamingMessageId,
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
              await connectToSSE(
                targetSessionId,
                currentRunId,
                streamingMessageId,
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
    [connectToSSE, clearReconnectTimeout, options],
  );

  // Send message
  const sendMessage = useCallback(
    async (
      content: string,
      agentOptions?: Record<string, boolean | string | number>,
      attachments?: MessageAttachment[],
    ) => {
      if (!content.trim()) return;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      isConnectingRef.current = false;
      clearReconnectTimeout();

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
            .generateTitle(newSessionId, content)
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
        }

        const streamSessionId = newSessionId || sessionId;
        const streamRunId = newRunId;

        if (!streamSessionId || !streamRunId) {
          throw new Error("Missing session_id or run_id");
        }

        isReconnectFromHistoryRef.current = false;
        await connectToSSE(streamSessionId, streamRunId, assistantMessage.id);
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
              ? { ...m, content: `Error: ${errorMessage}`, isStreaming: false }
              : m,
          ),
        );
        setConnectionStatus("disconnected");
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, currentAgent, connectToSSE, clearReconnectTimeout, options],
  );

  const stopGeneration = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setConnectionStatus("disconnected");
    streamingMessageIdRef.current = null;

    const currentSessionId = sessionIdRef.current;
    if (currentSessionId) {
      try {
        const { sessionApi } = await import("../services/api");
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
    clearReconnectTimeout();
  }, [clearReconnectTimeout]);

  const selectAgent = useCallback(
    (agentId: string) => {
      setCurrentAgent(agentId);
      clearMessages();
    },
    [clearMessages],
  );

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
        reconnectSSE();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [connectionStatus, reconnectSSE]);

  // Handle network status changes
  useEffect(() => {
    const handleOnline = () => {
      if (
        connectionStatus === "disconnected" &&
        sessionIdRef.current &&
        currentRunIdRef.current &&
        streamingMessageIdRef.current
      ) {
        reconnectSSE();
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
  }, [connectionStatus, reconnectSSE]);

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
    reconnectSSE,
  };
}
