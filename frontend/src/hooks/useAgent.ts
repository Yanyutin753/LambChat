import { useState, useCallback, useRef, useEffect } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  Message,
  ToolCall,
  ToolResult,
  AgentInfo,
  AgentListResponse,
  ToolPart,
  ConnectionStatus,
  SubagentPart,
  ThinkingPart,
  MessagePart,
  SandboxPart,
  TokenUsagePart,
} from "../types";
import {
  sessionApi,
  getAccessToken,
  type BackendSession,
} from "../services/api";

const API_BASE = "/api";

// Default agent type
const DEFAULT_AGENT = "search";

// Event types from backend
type EventType =
  | "metadata"
  | "message:chunk"
  | "user:message"
  | "thinking"
  | "tool:start"
  | "tool:result"
  | "todo:created"
  | "todo:updated"
  | "skill:loaded"
  | "agent:call"
  | "agent:result"
  | "observation"
  | "code"
  | "file"
  | "message:complete"
  | "workflow:step_start"
  | "workflow:step_end"
  | "approval_required"
  | "sandbox:starting"
  | "sandbox:state"
  | "sandbox:ready"
  | "sandbox:error"
  | "token:usage"
  | "done"
  | "error";

interface StreamEvent {
  event: EventType;
  data: string;
}

interface EventData {
  session_id?: string;
  agent_id?: string;
  agent_name?: string;
  tool?: string;
  args?: Record<string, unknown>;
  result?: string;
  success?: boolean;
  content?: string;
  thinking_id?: string;
  error?: string;
  type?: string;
  step_name?: string;
  step_id?: string;
  input?: string;
  depth?: number;
  // approval_required event fields
  id?: string;
  message?: string;
  choices?: string[];
  default?: string;
  // sandbox event fields
  state?: string;
  sandbox_id?: string;
  work_dir?: string;
  // token:usage event fields
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  duration?: number;
  timestamp?: string;
}

interface UseAgentOptions {
  onApprovalRequired?: (approval: {
    id: string;
    message: string;
    type: string;
    choices?: string[];
    default?: string;
  }) => void;
  onClearApprovals?: () => void; // 清除所有 approvals 的回调
  getEnabledTools?: () => string[]; // 获取启用的工具列表
}

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
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const retryCountRef = useRef(0);

  // Track processed event IDs to prevent duplicates
  const processedEventIdsRef = useRef<Set<string>>(new Set());

  // Track last event timestamp from history to prevent duplicates when reconnecting
  const lastHistoryTimestampRef = useRef<Date | null>(null);

  // 子代理追踪栈 - 用于追踪当前活动的子代理，支持并行子代理
  // 结构: [{ agent_id, depth, message_id }] - 按 depth 排序
  const activeSubagentStackRef = useRef<
    Array<{ agent_id: string; depth: number; message_id: string }>
  >([]);

  // Current streaming message ID
  const streamingMessageIdRef = useRef<string | null>(null);

  // Flag to indicate if current SSE connection is from loadHistory (reconnect scenario)
  // In this case, we should skip user:message events as they're already in history
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
      // This prevents duplicates when reconnecting to a running session
      // Only apply this filter if both timestamps are available and valid
      if (eventTimestamp && lastHistoryTimestampRef.current) {
        const eventTime = new Date(eventTimestamp);
        const historyTime = lastHistoryTimestampRef.current;
        // Use strict less than to avoid filtering events that happened at the exact same moment
        // (which could be new events that just happened to have the same timestamp)
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
        console.log(
          "[SSE] Event timestamp check passed:",
          eventTime.toISOString(),
          ">=",
          historyTime.toISOString(),
        );
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
          // SSE 中的 user:message 事件
          // 重要：即使是历史重连，也不能直接跳过 user:message 事件
          // 因为 MongoDB 写入可能有延迟，导致历史消息中缺少该事件
          // 我们通过内容去重来避免重复显示
          const userContent = data.content || "";
          if (userContent) {
            setMessages((prev) => {
              // 如果列表为空，说明是新会话，需要添加用户消息
              if (prev.length === 0) {
                console.log(
                  "[SSE] Adding user message to empty list:",
                  userContent.slice(0, 50),
                );
                const newUserMessage: Message = {
                  id: crypto.randomUUID(),
                  role: "user",
                  content: userContent,
                  timestamp: eventTimestamp
                    ? new Date(eventTimestamp)
                    : new Date(),
                };
                return [...prev, newUserMessage];
              }
              // 检查是否已存在相同内容的用户消息（避免重复）
              const existingUserMsg = prev.find(
                (m) => m.role === "user" && m.content === userContent,
              );
              if (existingUserMsg) {
                console.log(
                  "[SSE] User message already exists, skipping duplicate",
                );
                return prev;
              }
              // 新的用户消息（可能是 MongoDB 写入延迟导致历史中没有）
              console.log(
                "[SSE] Adding missing user message from SSE:",
                userContent.slice(0, 50),
              );
              const newUserMessage: Message = {
                id: crypto.randomUUID(),
                role: "user",
                content: userContent,
                timestamp: eventTimestamp
                  ? new Date(eventTimestamp)
                  : new Date(),
              };
              // 检查是否有一个正在 streaming 的 assistant 消息
              // 如果有，将用户消息插入到该消息之前
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
          const subagentPart: SubagentPart = {
            type: "subagent",
            agent_id: agentId,
            agent_name: data.agent_name || data.agent_id || "Unknown Agent",
            input: data.input || "",
            isPending: true,
            depth: depth,
            parts: [],
          };

          // 将子代理添加到活动栈中（用于后续事件的路由）
          activeSubagentStackRef.current.push({
            agent_id: agentId,
            depth: depth,
            message_id: messageId,
          });
          console.log(
            "[agent:call] Added to stack:",
            agentId,
            "depth:",
            depth,
            "stack size:",
            activeSubagentStackRef.current.length,
          );

          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              // 找到正确的嵌套位置并添加（使用返回的新数组）
              const newParts = addPartToDepth(
                parts,
                subagentPart,
                depth,
                agentId,
              );
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "agent:result": {
          const agentId = data.agent_id || "unknown";

          // 从活动栈中移除对应的子代理
          const stackIndex = activeSubagentStackRef.current.findIndex(
            (item) =>
              item.agent_id === agentId && item.message_id === messageId,
          );
          if (stackIndex !== -1) {
            activeSubagentStackRef.current.splice(stackIndex, 1);
            console.log(
              "[agent:result] Removed from stack:",
              agentId,
              "remaining stack size:",
              activeSubagentStackRef.current.length,
            );
          }

          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              // 找到对应的 SubagentPart 并更新（使用返回的新数组）
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
            const thinkingPart: ThinkingPart = {
              type: "thinking",
              content,
              thinking_id: thinkingId,
              depth,
              agent_id: data.agent_id,
              isStreaming: true,
            };
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== messageId) return m;
                const parts = m.parts || [];
                // 如果 depth > 0，添加到子代理内部（传入 agent_id 精确匹配）
                if (depth > 0) {
                  const newParts = addPartToDepth(
                    parts,
                    thinkingPart,
                    depth,
                    data.agent_id as string,
                    messageId, // 传入 messageId 用于栈匹配
                  );
                  return { ...m, parts: newParts };
                } else {
                  // 主代理的 thinking，根据 thinking_id 合并到同一个块或添加新的
                  const newParts = [...parts];
                  // 查找相同 thinking_id 的 thinking 块进行合并
                  const existingIndex = newParts.findIndex(
                    (p) =>
                      p.type === "thinking" &&
                      p.thinking_id === thinkingId &&
                      thinkingId !== undefined,
                  );
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
              if (!targetMessage) {
                console.warn(
                  "[handleStreamEvent] Message not found for chunk:",
                  messageId,
                  "Available messages:",
                  prev.map((m) => m.id),
                );
                return prev;
              }
              console.log(
                "[handleStreamEvent] Appending chunk to message:",
                messageId,
                "content length:",
                content.length,
                "depth:",
                depth,
              );
              return prev.map((m) => {
                if (m.id !== messageId) return m;
                const parts = m.parts || [];

                if (depth > 0) {
                  // 子代理的文本，添加到子代理内部（传入 agent_id 精确匹配）
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
                    data.agent_id as string,
                    messageId, // 传入 messageId 用于栈匹配
                  );
                  return { ...m, parts: newParts };
                } else {
                  // 主代理的文本
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
          const toolCall: ToolCall = {
            id: undefined,
            name: data.tool || "",
            args: data.args || {},
          };
          const toolPart: ToolPart = {
            type: "tool",
            name: data.tool || "",
            args: data.args || {},
            isPending: true,
            depth,
            agent_id: data.agent_id,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              let newParts: MessagePart[];

              if (depth > 0) {
                // 子代理的工具调用，传入 agent_id 精确匹配
                newParts = addPartToDepth(
                  parts,
                  toolPart,
                  depth,
                  data.agent_id as string,
                  messageId, // 传入 messageId 用于栈匹配
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
          const toolResult: ToolResult = {
            name: data.tool || "",
            result: data.result || "",
            success: !data.result?.startsWith("Error:"),
          };
          const toolName = data.tool || "";
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];

              if (depth > 0) {
                // 在子代理内部更新工具结果（传入 agent_id 精确匹配）
                const newParts = updateToolResultInDepth(
                  parts,
                  toolName,
                  toolResult.result,
                  toolResult.success,
                  depth,
                  data.agent_id as string,
                );
                return { ...m, parts: newParts };
              } else {
                // 主代理的工具结果
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
          // 清除所有 pending approvals，因为对话已经失败
          options?.onClearApprovals?.();
          break;
        }

        case "approval_required": {
          // 当 Agent 调用 ask_human 工具时，通过 SSE 推送此事件
          // 重要：需要检查 approval 状态，避免重复显示已回复的 approval
          console.log("[SSE] approval_required event received:", data);
          console.log(
            "[SSE] options?.onApprovalRequired exists:",
            !!options?.onApprovalRequired,
          );
          console.log("[SSE] data.id exists:", !!data.id);
          if (data.id && options?.onApprovalRequired) {
            // 检查 approval 状态，只有 pending 才触发回调
            fetch(`/human/${data.id}`)
              .then((response) => {
                if (response.ok) {
                  return response.json();
                }
                return null;
              })
              .then((approval) => {
                if (approval && approval.status === "pending") {
                  console.log("[SSE] Approval is pending, calling callback");
                  options?.onApprovalRequired?.({
                    id: data.id!,
                    message: approval.message || "",
                    type: approval.type || "text",
                    choices: approval.choices || [],
                    default: approval.default ?? null,
                  });
                } else {
                  console.log(
                    "[SSE] Approval already processed or not found:",
                    data.id,
                    "status:",
                    approval?.status,
                  );
                }
              })
              .catch((err) => {
                console.warn("[SSE] Failed to check approval status:", err);
              });
          } else {
            console.warn(
              "[SSE] approval_required event NOT processed - missing id or callback",
            );
          }
          break;
        }

        case "sandbox:starting": {
          console.log("[SSE] sandbox:starting event received");
          setIsInitializingSandbox(true);
          setSandboxError(null);
          // 同时添加到消息中显示
          const startingPart: SandboxPart = {
            type: "sandbox",
            status: "starting",
            timestamp: data.timestamp,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              // 替换任何现有的 sandbox 状态为 starting
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? startingPart : p))
                : [...parts, startingPart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "sandbox:state": {
          console.log("[SSE] sandbox:state event received:", data.state);
          // 更新 sandbox 状态到消息中显示
          const statePart: SandboxPart = {
            type: "sandbox",
            status: data.state as "starting" | "ready" | "error",
            timestamp: data.timestamp,
          };
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== messageId) return m;
              const parts = m.parts || [];
              // 替换任何现有的 sandbox 状态
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? statePart : p))
                : [...parts, statePart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "sandbox:ready": {
          console.log("[SSE] sandbox:ready event received:", data.sandbox_id);
          setIsInitializingSandbox(false);
          // 同时添加到消息中显示
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
              // 替换任何现有的 sandbox 状态为 ready
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? readyPart : p))
                : [...parts, readyPart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "sandbox:error": {
          console.log("[SSE] sandbox:error event received:", data.error);
          setIsInitializingSandbox(false);
          setSandboxError(data.error || "沙箱初始化失败");
          // 同时添加到消息中显示
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
              // 替换任何现有的 sandbox 状态为 error
              const newParts = parts.some((p) => p.type === "sandbox")
                ? parts.map((p) => (p.type === "sandbox" ? errorPart : p))
                : [...parts, errorPart];
              return { ...m, parts: newParts };
            }),
          );
          break;
        }

        case "token:usage": {
          console.log("[SSE] token:usage event received:", data);
          // 更新消息的 tokenUsage 和 duration
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
                duration: data.duration ? data.duration * 1000 : undefined, // 转换为毫秒
              };
            }),
          );
          break;
        }
      }
    },
    // Intentionally omit deps to avoid infinite re-render loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [options?.onApprovalRequired],
  );

  // 辅助函数：将 part 添加到正确的深度位置
  // 注意：子代理内部的 events 的 depth 等于子代理的 depth
  // 例如：子代理 depth=1，其内部事件也是 depth=1
  // 重要：返回新的 parts 数组（不可变更新）
  // 重要：使用 agent_id 精确匹配，支持多个并行子代理
  const addPartToDepth = (
    parts: MessagePart[],
    part: MessagePart,
    targetDepth: number,
    targetAgentId?: string, // 添加 agent_id 参数用于精确匹配
    messageId?: string, // 用于从栈中查找当前活动子代理
  ): MessagePart[] => {
    if (targetDepth <= 0) {
      // 合并相邻的文本块
      if (part.type === "text") {
        const lastPart = parts[parts.length - 1];
        if (lastPart?.type === "text" && !lastPart.depth) {
          // 创建新数组，更新最后一个元素
          const newParts = [...parts];
          newParts[newParts.length - 1] = {
            ...lastPart,
            content: lastPart.content + part.content,
          };
          return newParts;
        }
      }
      return [...parts, part];
    }

    // 如果没有指定 targetAgentId，尝试从活动栈中获取当前活动的子代理
    let effectiveAgentId = targetAgentId;
    if (!effectiveAgentId && messageId) {
      // 找到与当前消息相关的最深的活动子代理
      const relevantAgents = activeSubagentStackRef.current.filter(
        (item) =>
          item.message_id === messageId &&
          (item.depth === targetDepth || item.depth === targetDepth - 1),
      );
      if (relevantAgents.length > 0) {
        // 优先选择最深的（最后添加的）
        const lastAgent = relevantAgents[relevantAgents.length - 1];
        effectiveAgentId = lastAgent.agent_id;
        console.log(
          "[addPartToDepth] Using agent from stack:",
          effectiveAgentId,
          "depth:",
          targetDepth,
        );
      }
    }

    // 找到匹配的 subagent（使用 agent_id 精确匹配，支持并行子代理）
    // 注意：子代理内部事件的 depth 等于子代理自身的 depth
    // 所以我们需要找到 depth === targetDepth 且 agent_id 匹配的子代理
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      if (p.type === "subagent" && p.depth === targetDepth && p.isPending) {
        // 如果有 agent_id，需要精确匹配
        if (effectiveAgentId && p.agent_id !== effectiveAgentId) {
          continue; // 跳过不匹配的子代理
        }
        // 创建新的 subagent 对象和 parts 数组
        const existingParts = p.parts || [];
        let newSubagentParts: MessagePart[];

        // 合并相邻的文本块或 thinking 块
        if (part.type === "text") {
          const lastPart = existingParts[existingParts.length - 1];
          if (lastPart?.type === "text") {
            newSubagentParts = [...existingParts];
            newSubagentParts[newSubagentParts.length - 1] = {
              ...lastPart,
              content: lastPart.content + part.content,
            };
          } else {
            newSubagentParts = [...existingParts, part];
          }
        } else if (part.type === "thinking") {
          // 子代理的 thinking 合并逻辑：根据 thinking_id 合并
          const thinkingId = part.thinking_id;
          const existingIndex = existingParts.findIndex(
            (p) =>
              p.type === "thinking" &&
              p.thinking_id === thinkingId &&
              thinkingId !== undefined,
          );
          if (existingIndex >= 0) {
            // 找到相同 thinking_id 的块，合并内容
            const existing = existingParts[existingIndex] as ThinkingPart;
            newSubagentParts = [...existingParts];
            newSubagentParts[existingIndex] = {
              ...existing,
              content: existing.content + part.content,
              isStreaming: true,
            };
          } else {
            newSubagentParts = [...existingParts, part];
          }
        } else {
          newSubagentParts = [...existingParts, part];
        }

        // 创建新的 parts 数组和新的 subagent 对象
        const newParts = [...parts];
        newParts[i] = { ...p, parts: newSubagentParts };
        return newParts;
      }
      // 递归查找嵌套的 subagent（处理多层嵌套的情况）
      if (p.type === "subagent" && p.parts) {
        const result = findAndAddToSubagent(
          p,
          part,
          targetDepth,
          effectiveAgentId,
        );
        if (result) {
          const newParts = [...parts];
          newParts[i] = result;
          return newParts;
        }
      }
    }
    // 如果没找到匹配的子代理，记录警告并添加到顶层
    console.warn(
      "[addPartToDepth] No matching subagent found for depth:",
      targetDepth,
      "agent_id:",
      effectiveAgentId,
      "adding to top level",
    );
    return [...parts, part];
  };

  // 递归查找并添加到子代理，返回更新后的 subagent 或 null
  const findAndAddToSubagent = (
    subagent: SubagentPart,
    part: MessagePart,
    targetDepth: number,
    targetAgentId?: string, // 添加 agent_id 参数
  ): SubagentPart | null => {
    // 子代理内部事件的 depth 与子代理自身的 depth 相同
    // 所以当 subagent.depth === targetDepth 时，我们需要检查 agent_id
    if (subagent.depth === targetDepth && subagent.isPending) {
      // 如果有 agent_id，需要精确匹配
      if (targetAgentId && subagent.agent_id !== targetAgentId) {
        // 不匹配，继续递归查找嵌套的子代理
      } else {
        // 匹配成功，添加到这个子代理的 parts 中
        const existingParts = subagent.parts || [];
        let newParts: MessagePart[];

        // 合并相邻的文本块或 thinking 块
        if (part.type === "text") {
          const lastPart = existingParts[existingParts.length - 1];
          if (lastPart?.type === "text") {
            newParts = [...existingParts];
            newParts[newParts.length - 1] = {
              ...lastPart,
              content: lastPart.content + part.content,
            };
          } else {
            newParts = [...existingParts, part];
          }
        } else if (part.type === "thinking") {
          // 子代理的 thinking 合并逻辑（与主代理类似）
          const thinkingId = part.thinking_id;
          const existingIndex = existingParts.findIndex(
            (p) =>
              p.type === "thinking" &&
              p.thinking_id === thinkingId &&
              thinkingId !== undefined,
          );
          if (existingIndex >= 0) {
            // 找到相同 thinking_id 的块，合并内容
            const existing = existingParts[existingIndex] as ThinkingPart;
            newParts = [...existingParts];
            newParts[existingIndex] = {
              ...existing,
              content: existing.content + part.content,
              isStreaming: true,
            };
          } else {
            newParts = [...existingParts, part];
          }
        } else {
          newParts = [...existingParts, part];
        }

        return { ...subagent, parts: newParts };
      }
    }

    // 递归查找嵌套的子代理
    if (subagent.parts) {
      for (let i = subagent.parts.length - 1; i >= 0; i--) {
        const p = subagent.parts[i];
        if (p.type === "subagent") {
          const result = findAndAddToSubagent(
            p as SubagentPart,
            part,
            targetDepth,
            targetAgentId,
          );
          if (result) {
            const newParts = [...subagent.parts];
            newParts[i] = result;
            return { ...subagent, parts: newParts };
          }
        }
      }
    }
    return null;
  };

  // 辅助函数：更新子代理结果（返回新的 parts 数组）
  const updateSubagentResult = (
    parts: MessagePart[],
    agentId: string,
    result: string,
    success: boolean,
    targetDepth: number,
  ): MessagePart[] => {
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      if (
        p.type === "subagent" &&
        p.agent_id === agentId &&
        p.depth === targetDepth &&
        p.isPending
      ) {
        const newParts = [...parts];
        newParts[i] = {
          ...p,
          result,
          success,
          isPending: false,
        };
        return newParts;
      }
      if (p.type === "subagent" && p.parts) {
        const updatedSubagent = updateSubagentResultInParts(
          p.parts,
          agentId,
          result,
          success,
          targetDepth,
        );
        if (updatedSubagent) {
          const newParts = [...parts];
          newParts[i] = { ...p, parts: updatedSubagent };
          return newParts;
        }
      }
    }
    return parts;
  };

  const updateSubagentResultInParts = (
    parts: MessagePart[],
    agentId: string,
    result: string,
    success: boolean,
    targetDepth: number,
  ): MessagePart[] | null => {
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      if (
        p.type === "subagent" &&
        p.agent_id === agentId &&
        p.depth === targetDepth &&
        p.isPending
      ) {
        const newParts = [...parts];
        newParts[i] = {
          ...p,
          result,
          success,
          isPending: false,
        };
        return newParts;
      }
      if (p.type === "subagent" && p.parts) {
        const updatedParts = updateSubagentResultInParts(
          p.parts,
          agentId,
          result,
          success,
          targetDepth,
        );
        if (updatedParts) {
          const newParts = [...parts];
          newParts[i] = { ...p, parts: updatedParts };
          return newParts;
        }
      }
    }
    return null;
  };

  // 辅助函数：在指定深度更新工具结果（返回新的 parts 数组）
  const updateToolResultInDepth = (
    parts: MessagePart[],
    toolName: string,
    result: string,
    success: boolean,
    targetDepth: number,
    targetAgentId?: string, // 添加 agent_id 参数
  ): MessagePart[] => {
    // 先查找子代理内部
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      if (p.type === "subagent" && p.parts) {
        // 如果有 agent_id，需要精确匹配
        if (targetAgentId && p.agent_id !== targetAgentId) {
          continue;
        }
        const updatedParts = updateToolResultInParts(
          p.parts,
          toolName,
          result,
          success,
          targetDepth,
        );
        if (updatedParts) {
          const newParts = [...parts];
          newParts[i] = { ...p, parts: updatedParts };
          return newParts;
        }
      }
    }
    return parts;
  };

  const updateToolResultInParts = (
    parts: MessagePart[],
    toolName: string,
    result: string,
    success: boolean,
    targetDepth: number,
  ): MessagePart[] | null => {
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (p.type === "tool" && p.name === toolName && p.isPending) {
        const newParts = [...parts];
        newParts[i] = {
          ...p,
          result,
          success,
          isPending: false,
        };
        return newParts;
      }
      if (p.type === "subagent" && p.parts) {
        const updatedParts = updateToolResultInParts(
          p.parts,
          toolName,
          result,
          success,
          targetDepth,
        );
        if (updatedParts) {
          const newParts = [...parts];
          newParts[i] = { ...p, parts: updatedParts };
          return newParts;
        }
      }
    }
    return null;
  };

  // Connect to SSE stream
  const connectToSSE = useCallback(
    async (targetSessionId: string, targetRunId: string, messageId: string) => {
      // Prevent duplicate connections
      if (isConnectingRef.current) {
        console.log("[SSE] Connection already in progress, skipping...");
        return;
      }
      isConnectingRef.current = true;
      streamingMessageIdRef.current = messageId;

      // Abort any existing connection
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
                // Parse data to extract timestamp for deduplication
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

    // Check task status
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
        // Find the message and get last processed event
        const msgs = messages;
        const lastMsg = msgs.find((m) => m.id === currentMsgId);
        if (lastMsg) {
          // 标记这是重连，跳过 user:message 事件
          isReconnectFromHistoryRef.current = true;
          // Use a fresh connection since we're tracking processed IDs
          await connectToSSE(currentSessId, currentRId, currentMsgId);
        }
      }
    }, delay);
  }, [clearReconnectTimeout, getReconnectDelay, connectToSSE, messages]);

  // Load message history from backend (only for completed sessions)
  const loadHistory = useCallback(
    async (targetSessionId: string, targetRunId?: string) => {
      // 先断开现有的 SSE 连接，清除相关状态
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      isConnectingRef.current = false;
      streamingMessageIdRef.current = null;
      clearReconnectTimeout();

      setIsLoading(true);
      setError(null);

      // Clear processed events and history timestamp for new session
      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;

      try {
        const sessionData = await sessionApi.get(targetSessionId);

        if (sessionData) {
          setSessionId(targetSessionId);

          // Get current run_id for potential SSE reconnection (only if task is running)
          const currentRunId =
            targetRunId ||
            (sessionData.metadata?.current_run_id as string) ||
            null;

          // First check if current task is still running
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
              console.log(
                "[loadHistory] Current run status:",
                statusData.status,
                "isTaskRunning:",
                isTaskRunning,
              );
            } catch (statusErr) {
              console.warn("[loadHistory] Failed to check status:", statusErr);
            }
          }

          // Load ALL events from the session (not just current run)
          // This shows complete conversation history across all runs
          const eventsData = await sessionApi.getEvents(targetSessionId);

          if (eventsData.events && eventsData.events.length > 0) {
            // 按时间戳排序事件，确保消息顺序正确
            const sortedEvents = [...eventsData.events].sort((a, b) => {
              const timeA = new Date(a.timestamp || 0).getTime();
              const timeB = new Date(b.timestamp || 0).getTime();
              return timeA - timeB;
            });

            const reconstructedMessages: Message[] = [];
            let currentAssistantMessage: Message | null = null;

            for (const event of sortedEvents) {
              const eventType = event.event_type;
              const eventData = event.data as {
                content?: string;
                tool?: string;
                args?: Record<string, unknown>;
                result?: string;
                success?: boolean;
                depth?: number;
                agent_id?: string;
                agent_name?: string;
                input?: string;
                timestamp?: string;
                sandbox_id?: string;
                work_dir?: string;
                error?: string;
              };
              const depth = eventData.depth || 0;
              const agentId = eventData.agent_id;

              // Track processed event IDs
              if (event.id) {
                processedEventIdsRef.current.add(event.id.toString());
              }

              // 处理 approval_required 事件
              // 需要检查这个 approval 是否已经有回复（通过调用后端接口）
              // 如果没有回复，才触发 onApprovalRequired 回调
              if (eventType === "approval_required") {
                const approvalData = eventData as {
                  id?: string;
                  message?: string;
                  type?: string;
                  choices?: string[];
                  default?: string;
                };
                if (approvalData.id && options?.onApprovalRequired) {
                  // 检查 approval 状态
                  try {
                    const response = await fetch(`/human/${approvalData.id}`);
                    if (response.ok) {
                      const approval = await response.json();
                      // 只有 pending 状态的 approval 才需要显示
                      if (approval.status === "pending") {
                        console.log(
                          "[loadHistory] Found pending approval:",
                          approvalData.id,
                        );
                        options.onApprovalRequired({
                          id: approvalData.id,
                          message: approvalData.message || "",
                          type: approvalData.type || "text",
                          choices: approvalData.choices,
                          default: approvalData.default,
                        });
                      } else {
                        console.log(
                          "[loadHistory] Approval already processed:",
                          approvalData.id,
                          "status:",
                          approval.status,
                        );
                      }
                    } else {
                      // approval 不存在（可能已被清理），跳过
                      console.log(
                        "[loadHistory] Approval not found (likely cleaned up):",
                        approvalData.id,
                      );
                    }
                  } catch (e) {
                    console.warn(
                      "[loadHistory] Failed to check approval status:",
                      e,
                    );
                  }
                }
                continue;
              }

              if (eventType === "user:message") {
                if (currentAssistantMessage) {
                  reconstructedMessages.push(currentAssistantMessage);
                  currentAssistantMessage = null;
                }
                reconstructedMessages.push({
                  id: crypto.randomUUID(),
                  role: "user",
                  content: eventData.content || "",
                  timestamp: new Date(event.timestamp || Date.now()),
                });
              } else if (eventType === "agent:call") {
                // 创建子代理
                if (!currentAssistantMessage) {
                  currentAssistantMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: "",
                    timestamp: new Date(event.timestamp || Date.now()),
                    parts: [],
                    isStreaming: false,
                  };
                }
                const subagentPart: SubagentPart = {
                  type: "subagent",
                  agent_id: agentId || "unknown",
                  agent_name:
                    eventData.agent_name || agentId || "Unknown Agent",
                  input: eventData.input || "",
                  isPending: true,
                  depth: depth,
                  parts: [],
                };
                const parts = currentAssistantMessage.parts || [];
                currentAssistantMessage.parts = addPartToDepth(
                  parts,
                  subagentPart,
                  depth,
                  agentId || "unknown", // 传入 agentId 用于精确匹配
                );
              } else if (eventType === "agent:result") {
                // 更新子代理结果
                if (currentAssistantMessage) {
                  const parts = currentAssistantMessage.parts || [];
                  currentAssistantMessage.parts = updateSubagentResult(
                    parts,
                    agentId || "unknown",
                    eventData.result || "",
                    eventData.success !== false,
                    depth,
                  );
                }
              } else if (eventType === "thinking") {
                // 处理 thinking 事件
                if (!currentAssistantMessage) {
                  currentAssistantMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: "",
                    timestamp: new Date(event.timestamp || Date.now()),
                    parts: [],
                    isStreaming: false,
                  };
                }
                const thinkingPart: ThinkingPart = {
                  type: "thinking",
                  content: eventData.content || "",
                  depth,
                  agent_id: agentId,
                };
                const parts = currentAssistantMessage.parts || [];
                if (depth > 0) {
                  currentAssistantMessage.parts = addPartToDepth(
                    parts,
                    thinkingPart,
                    depth,
                    agentId,
                  );
                } else {
                  const newParts = [...parts];
                  const lastPart = newParts[newParts.length - 1];
                  if (lastPart?.type === "thinking") {
                    newParts[newParts.length - 1] = {
                      ...lastPart,
                      content: lastPart.content + (eventData.content || ""),
                    };
                  } else {
                    newParts.push(thinkingPart);
                  }
                  currentAssistantMessage.parts = newParts;
                }
              } else if (eventType === "message:chunk") {
                if (!currentAssistantMessage) {
                  currentAssistantMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: "",
                    timestamp: new Date(event.timestamp || Date.now()),
                    parts: [],
                    isStreaming: false,
                  };
                }
                const content = eventData.content || "";
                if (depth > 0) {
                  // 子代理的文本，使用 addPartToDepth
                  const textPart = {
                    type: "text" as const,
                    content,
                    depth,
                    agent_id: agentId,
                  };
                  const parts = currentAssistantMessage.parts || [];
                  currentAssistantMessage.parts = addPartToDepth(
                    parts,
                    textPart,
                    depth,
                    agentId,
                  );
                } else {
                  // 主代理的文本
                  currentAssistantMessage.content += content;
                  const parts = currentAssistantMessage.parts || [];
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
                  currentAssistantMessage.parts = newParts;
                }
              } else if (eventType === "tool:start") {
                // 如果 currentAssistantMessage 不存在，先创建它
                if (!currentAssistantMessage) {
                  currentAssistantMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: "",
                    timestamp: new Date(event.timestamp || Date.now()),
                    parts: [],
                    isStreaming: false,
                  };
                }
                const toolCall: ToolCall = {
                  id: undefined,
                  name: eventData.tool || "",
                  args: eventData.args || {},
                };
                const toolPart: ToolPart = {
                  type: "tool",
                  name: eventData.tool || "",
                  args: eventData.args || {},
                  isPending: true,
                  depth,
                  agent_id: agentId,
                };
                const parts = currentAssistantMessage.parts || [];
                if (depth > 0) {
                  currentAssistantMessage.parts = addPartToDepth(
                    parts,
                    toolPart,
                    depth,
                    agentId,
                  );
                } else {
                  currentAssistantMessage.parts = [...parts, toolPart];
                  // 主代理的工具调用，添加到 toolCalls
                  currentAssistantMessage.toolCalls = [
                    ...(currentAssistantMessage.toolCalls || []),
                    toolCall,
                  ];
                }
              } else if (eventType === "tool:result") {
                // 如果 currentAssistantMessage 不存在，跳过（没有对应的 tool:start）
                if (!currentAssistantMessage) {
                  continue;
                }
                const toolResult: ToolResult = {
                  name: eventData.tool || "",
                  result: eventData.result || "",
                  success: !eventData.result?.toString().startsWith("Error:"),
                };
                const toolName = eventData.tool || "";
                const parts = currentAssistantMessage.parts || [];
                if (depth > 0) {
                  currentAssistantMessage.parts = updateToolResultInDepth(
                    parts,
                    toolName,
                    eventData.result || "",
                    eventData.success !== false,
                    depth,
                    agentId,
                  );
                } else {
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
                        result: eventData.result || "",
                        success: eventData.success !== false,
                        isPending: false,
                      } as ToolPart;
                    }
                    return p;
                  });
                  currentAssistantMessage.parts = newParts;
                  // 主代理的工具结果，添加到 toolResults
                  currentAssistantMessage.toolResults = [
                    ...(currentAssistantMessage.toolResults || []),
                    toolResult,
                  ];
                }
              } else if (eventType === "sandbox:starting") {
                // Sandbox 开始初始化
                if (!currentAssistantMessage) {
                  currentAssistantMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: "",
                    timestamp: new Date(event.timestamp || Date.now()),
                    parts: [],
                    isStreaming: false,
                  };
                }
                const sandboxPart: SandboxPart = {
                  type: "sandbox",
                  status: "starting",
                  timestamp: eventData.timestamp,
                };
                const parts = currentAssistantMessage.parts || [];
                currentAssistantMessage.parts = [...parts, sandboxPart];
              } else if (eventType === "sandbox:ready") {
                // Sandbox 就绪
                if (!currentAssistantMessage) {
                  currentAssistantMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: "",
                    timestamp: new Date(event.timestamp || Date.now()),
                    parts: [],
                    isStreaming: false,
                  };
                }
                const sandboxPart: SandboxPart = {
                  type: "sandbox",
                  status: "ready",
                  sandbox_id: eventData.sandbox_id,
                  work_dir: eventData.work_dir,
                  timestamp: eventData.timestamp,
                };
                const parts = currentAssistantMessage.parts || [];
                // 替换 starting 为 ready
                const newParts = parts.map((p) =>
                  p.type === "sandbox" && p.status === "starting"
                    ? sandboxPart
                    : p,
                );
                currentAssistantMessage.parts = newParts;
              } else if (eventType === "sandbox:error") {
                // Sandbox 错误
                if (!currentAssistantMessage) {
                  currentAssistantMessage = {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: "",
                    timestamp: new Date(event.timestamp || Date.now()),
                    parts: [],
                    isStreaming: false,
                  };
                }
                const sandboxPart: SandboxPart = {
                  type: "sandbox",
                  status: "error",
                  error: eventData.error,
                  timestamp: eventData.timestamp,
                };
                const parts = currentAssistantMessage.parts || [];
                // 替换任何 sandbox 状态为 error
                const newParts = parts.map((p) =>
                  p.type === "sandbox" ? sandboxPart : p,
                );
                currentAssistantMessage.parts = newParts;
              } else if (eventType === "token:usage") {
                // Token 使用统计
                // 从 event.data 中获取
                const tokenData = event.data as {
                  input_tokens?: number;
                  output_tokens?: number;
                  total_tokens?: number;
                  duration?: number;
                };
                if (currentAssistantMessage) {
                  currentAssistantMessage.tokenUsage = {
                    type: "token_usage",
                    input_tokens: tokenData.input_tokens || 0,
                    output_tokens: tokenData.output_tokens || 0,
                    total_tokens: tokenData.total_tokens || 0,
                  };
                  currentAssistantMessage.duration = tokenData.duration
                    ? tokenData.duration * 1000
                    : undefined;
                }
              }
            }

            if (currentAssistantMessage) {
              reconstructedMessages.push(currentAssistantMessage);
            }

            // Record the last event timestamp to prevent duplicates when reconnecting
            // Use sortedEvents to get the actual last event by time
            const lastEvent = sortedEvents[sortedEvents.length - 1];
            if (lastEvent?.timestamp) {
              lastHistoryTimestampRef.current = new Date(lastEvent.timestamp);
              console.log(
                "[loadHistory] Recorded last event timestamp:",
                lastHistoryTimestampRef.current.toISOString(),
              );
            }

            setMessages(reconstructedMessages);
            console.log(
              "[loadHistory] Loaded",
              reconstructedMessages.length,
              "messages from session",
            );

            // Only connect to SSE if current task is STILL running
            if (isTaskRunning && currentRunId) {
              setCurrentRunId(currentRunId);
              console.log(
                "[loadHistory] Task still running, will connect to SSE for new events...",
              );

              // 重要：当 completed_only=True 时，历史中只有已完成的 trace 的事件
              // 当前正在运行的 run 的事件不在历史中，需要从 SSE 获取
              // 因此，总是创建新的 assistant 消息来接收当前 run 的 SSE 事件
              //
              // 注意：不能复用历史中的 assistant 消息，因为那是之前 run 的消息！
              // 否则会导致当前 run 的事件被追加到之前的 assistant 消息上
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
              console.log(
                "[loadHistory] Created new assistant message for current run:",
                streamingMessageId,
              );

              // 标记这是从历史重连的 SSE，但不要跳过 user:message
              // 因为当前 run 的 user:message 可能不在历史中
              isReconnectFromHistoryRef.current = false;
              await connectToSSE(
                targetSessionId,
                currentRunId,
                streamingMessageId,
              );
            } else {
              console.log(
                "[loadHistory] Task completed, no SSE connection needed",
              );
            }
          } else {
            // 没有历史事件，但如果任务正在运行，仍然需要连接 SSE
            setMessages([]);

            if (isTaskRunning && currentRunId) {
              setCurrentRunId(currentRunId);
              console.log(
                "[loadHistory] No events but task running, will connect to SSE...",
              );
              // 没有历史事件，需要处理 user:message
              isReconnectFromHistoryRef.current = false;
              // 创建一个新的 assistant 消息用于接收流式数据
              // 注意：user:message 事件会将用户消息插入到这个 assistant 消息之前
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
      }
    },
    // Intentionally omit deps to avoid infinite re-render loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [connectToSSE, clearReconnectTimeout],
  );

  // Send message
  const sendMessage = useCallback(
    async (
      content: string,
      agentOptions?: Record<string, boolean | string | number>,
    ) => {
      if (!content.trim()) return;

      // Abort any existing connection
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      isConnectingRef.current = false;
      clearReconnectTimeout();

      // Clear processed events and history timestamp for new message
      processedEventIdsRef.current.clear();
      lastHistoryTimestampRef.current = null;

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: content.trim(),
        timestamp: new Date(),
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

      console.log("[sendMessage] Creating new messages:", {
        userMessageId: userMessage.id,
        assistantMessageId: assistantMessage.id,
        currentMessagesCount: messages.length,
      });

      setMessages((prev) => {
        console.log(
          "[sendMessage] Previous messages:",
          prev.map((m) => ({
            id: m.id,
            role: m.role,
            contentLength: m.content.length,
          })),
        );
        const newMessages = [...prev, userMessage, assistantMessage];
        console.log(
          "[sendMessage] New messages:",
          newMessages.map((m) => ({
            id: m.id,
            role: m.role,
            contentLength: m.content.length,
          })),
        );
        return newMessages;
      });
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

        // Submit task
        const disabledTools = options?.getEnabledTools?.();
        console.log("[sendMessage] Disabled tools:", disabledTools);
        const submitResponse = await fetch(
          `${API_BASE}/chat/stream?agent_id=${currentAgent}`,
          {
            method: "POST",
            headers,
            body: JSON.stringify({
              message: content,
              session_id: sessionId,
              // 发送 disabled_tools 数组，表示用户禁用的工具
              // 后端会根据此列表过滤掉被禁用的工具
              disabled_tools: disabledTools,
              // 发送 agent 选项（如 enable_thinking）
              agent_options: agentOptions,
            }),
          },
        );

        if (!submitResponse.ok) {
          throw new Error(`Submit failed: ${submitResponse.status}`);
        }

        const submitData = await submitResponse.json();
        const newSessionId = submitData.session_id;
        const newRunId = submitData.run_id;

        console.log("[sendMessage] Got response:", {
          session_id: newSessionId,
          run_id: newRunId,
        });

        if (!sessionId && newSessionId) {
          setSessionId(newSessionId);
          // Create a minimal session object for optimistic sidebar update
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

          // Auto-generate title for new session
          sessionApi
            .generateTitle(newSessionId, content)
            .then((result) => {
              // Update the session with the generated title
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

        // 标记这是新发送的消息，需要处理 user:message
        isReconnectFromHistoryRef.current = false;
        // Connect to SSE immediately
        console.log("[sendMessage] Connecting to SSE...");
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
    // Intentionally omit deps to avoid infinite re-render loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sessionId, currentAgent, connectToSSE, clearReconnectTimeout],
  );

  const stopGeneration = useCallback(async () => {
    // 1. 中断本地 SSE 连接
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setConnectionStatus("disconnected");
    streamingMessageIdRef.current = null;

    // 2. 调用后端取消 API（通知其他实例也取消任务）
    const currentSessionId = sessionIdRef.current;
    if (currentSessionId) {
      try {
        const { sessionApi } = await import("../services/api");
        await sessionApi.cancel(currentSessionId);
        console.log("[stopGeneration] Backend cancel API called successfully");
      } catch (error) {
        console.error(
          "[stopGeneration] Failed to call backend cancel API:",
          error,
        );
        // 不抛出错误，本地中断已经完成
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
    activeSubagentStackRef.current = []; // 清空子代理栈
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
        console.log("[SSE] Tab visible again, attempting reconnect...");
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
      console.log("[SSE] Network back online");
      if (
        connectionStatus === "disconnected" &&
        sessionIdRef.current &&
        currentRunIdRef.current &&
        streamingMessageIdRef.current
      ) {
        console.log("[SSE] Reconnecting after network restoration...");
        reconnectSSE();
      }
    };

    const handleOffline = () => {
      console.log("[SSE] Network offline");
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
