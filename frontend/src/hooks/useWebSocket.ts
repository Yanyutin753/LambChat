import type { SessionReadScope } from "../services/api/session";
import { useEffect, useRef, useCallback, useMemo, useState } from "react";
import {
  getValidAccessToken,
  refreshAccessToken,
} from "../services/api/tokenManager";
import { getRefreshToken } from "../services/api";
import { buildWebSocketUrl } from "../services/api/config";

export interface TaskCompleteNotification {
  type: "task:complete";
  data: {
    session_id: string;
    run_id: string;
    status: "completed" | "failed" | "waiting_human";
    id?: string;
    created_at?: string;
    dedupe_key?: string;
    notification_kind?: string;
    parent_session_id?: string;
    goal_status?: string;
    message?: string;
    unread_count?: number;
    project_id?: string | null;
    scheduled_task_id?: string | null;
    is_favorite?: boolean;
  };
}

export interface RecommendQuestionsNotification {
  type: "recommend:questions";
  data: {
    session_id: string;
    run_id: string;
    questions: string[];
  };
}

export interface UsageUpdatedNotification {
  type: "usage:updated";
  data: {
    trace_id: string;
  };
}

export interface SandboxPresenceNotification {
  type: "sandbox:presence";
  data: {
    machines: Array<{
      machine_id: string;
      name: string;
      platform: string;
      version: string;
      confirm_policy: string;
      online: boolean;
      last_seen?: number | null;
    }>;
    default_machine_id: string | null;
    legacy_online: boolean;
    revision: number;
  };
}

export interface WebSocketMessageHandlers {
  onSessionsRead?: (scope: SessionReadScope) => void;
  onTaskComplete?: (notification: TaskCompleteNotification) => void;
  onRecommendQuestions?: (notification: RecommendQuestionsNotification) => void;
  onUsageUpdated?: (notification: UsageUpdatedNotification) => void;
  onSandboxPresence?: (notification: SandboxPresenceNotification) => void;
  onSessionTaskStatus?: (data: {
    session_id: string;
    task_status: string;
  }) => void;
  /** 连接认证通过（auth:ok）：消费方可据此收紧推送依赖、放宽轮询。 */
  onWsOpen?: () => void;
  /** 连接关闭（含手动断开）：消费方回落到轮询对账。 */
  onWsClose?: () => void;
}

interface UseWebSocketOptions extends WebSocketMessageHandlers {
  enabled?: boolean;
  userId?: string;
}

export function dispatchWebSocketMessage(
  message: unknown,
  handlers: WebSocketMessageHandlers,
): void {
  if (!message || typeof message !== "object" || !("type" in message)) return;
  const typedMessage = message as { type?: unknown };
  if (typedMessage.type === "sessions:read") {
    const data = (message as { data?: unknown }).data;
    if (!data || typeof data !== "object" || Array.isArray(data)) return;
    const payload = data as Record<string, unknown>;
    const fields = ["session_id", "project_id", "scheduled_task_id"];
    if (
      Object.entries(payload).some(
        ([key, value]) =>
          !fields.includes(key) || typeof value !== "string" || !value,
      )
    )
      return;
    handlers.onSessionsRead?.({
      ...(payload.session_id
        ? { sessionId: payload.session_id as string }
        : {}),
      ...(payload.project_id
        ? { projectId: payload.project_id as string }
        : {}),
      ...(payload.scheduled_task_id
        ? { scheduledTaskId: payload.scheduled_task_id as string }
        : {}),
    });
  } else if (typedMessage.type === "task:complete") {
    handlers.onTaskComplete?.(message as TaskCompleteNotification);
  } else if (typedMessage.type === "recommend:questions") {
    const data = (message as { data?: unknown }).data;
    if (!data || typeof data !== "object") return;
    const payload = data as Record<string, unknown>;
    if (
      typeof payload.session_id !== "string" ||
      typeof payload.run_id !== "string" ||
      !Array.isArray(payload.questions) ||
      !payload.questions.every((question) => typeof question === "string")
    ) {
      return;
    }
    handlers.onRecommendQuestions?.(message as RecommendQuestionsNotification);
  } else if (typedMessage.type === "usage:updated") {
    const data = (message as { data?: unknown }).data;
    if (!data || typeof data !== "object") return;
    const payload = data as Record<string, unknown>;
    if (typeof payload.trace_id !== "string") return;
    handlers.onUsageUpdated?.(message as UsageUpdatedNotification);
  } else if (typedMessage.type === "sandbox:presence") {
    const data = (message as { data?: unknown }).data;
    if (!data || typeof data !== "object") return;
    const payload = data as Record<string, unknown>;
    if (typeof payload.revision !== "number") return;
    if (!Array.isArray(payload.machines)) return;
    const machinesOk = payload.machines.every(
      (machine) =>
        machine &&
        typeof machine === "object" &&
        typeof (machine as Record<string, unknown>).machine_id === "string" &&
        (machine as Record<string, unknown>).machine_id,
    );
    if (!machinesOk) return;
    handlers.onSandboxPresence?.(message as SandboxPresenceNotification);
  } else if (typedMessage.type === "session:task_status") {
    const data = (message as { data?: unknown }).data;
    if (data && typeof data === "object") {
      const payload = data as Record<string, unknown>;
      if (
        typeof payload.session_id === "string" &&
        typeof payload.task_status === "string"
      ) {
        handlers.onSessionTaskStatus?.({
          session_id: payload.session_id,
          task_status: payload.task_status,
        });
      }
    }
  }
}

// Exponential backoff configuration
const INITIAL_RECONNECT_DELAY = 1000; // 1 second
const MAX_RECONNECT_DELAY = 30000; // 30 seconds
const RECONNECT_DELAY_MULTIPLIER = 1.5;
const MAX_AUTH_FAILURES = 3; // Switch to long interval after this many consecutive 401s
const AUTH_FAILURE_COOLDOWN = 5 * 60 * 1000; // 5 minutes cooldown after max failures

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    onTaskComplete,
    onSessionsRead,
    onRecommendQuestions,
    onUsageUpdated,
    onSandboxPresence,
    onSessionTaskStatus,
    onWsOpen,
    onWsClose,
    enabled = true,
    userId,
  } = options;
  const scope = useMemo(() => ({ userId, enabled }), [userId, enabled]);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  const connectionVersionRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const onSessionsReadRef = useRef(onSessionsRead);
  onSessionsReadRef.current = onSessionsRead;
  const onTaskCompleteRef = useRef(onTaskComplete);
  const onRecommendQuestionsRef = useRef(onRecommendQuestions);
  const onUsageUpdatedRef = useRef(onUsageUpdated);
  const onSandboxPresenceRef = useRef(onSandboxPresence);
  const onSessionTaskStatusRef = useRef(onSessionTaskStatus);
  const onWsOpenRef = useRef(onWsOpen);
  const onWsCloseRef = useRef(onWsClose);
  const isMountedRef = useRef(true);
  const [isConnected, setIsConnected] = useState(false);

  // Track connection state to prevent race conditions
  const isConnectingRef = useRef(false);
  const isDisconnectingRef = useRef(false);

  // Exponential backoff state
  const reconnectAttemptRef = useRef(0);
  // Consecutive auth failure counter
  const authFailureCountRef = useRef(0);

  // Update ref when callback changes
  useEffect(() => {
    onTaskCompleteRef.current = onTaskComplete;
  }, [onTaskComplete]);

  useEffect(() => {
    onRecommendQuestionsRef.current = onRecommendQuestions;
  }, [onRecommendQuestions]);

  useEffect(() => {
    onUsageUpdatedRef.current = onUsageUpdated;
  }, [onUsageUpdated]);

  useEffect(() => {
    onSandboxPresenceRef.current = onSandboxPresence;
  }, [onSandboxPresence]);

  useEffect(() => {
    onWsOpenRef.current = onWsOpen;
  }, [onWsOpen]);

  useEffect(() => {
    onWsCloseRef.current = onWsClose;
  }, [onWsClose]);

  useEffect(() => {
    onSessionTaskStatusRef.current = onSessionTaskStatus;
  }, [onSessionTaskStatus]);

  const connect = useCallback(async () => {
    const generation = connectionVersionRef.current;
    const isCurrent = () =>
      isMountedRef.current &&
      enabled &&
      scopeRef.current === scope &&
      connectionVersionRef.current === generation;
    // Prevent multiple simultaneous connection attempts
    if (!isCurrent() || isConnectingRef.current || isDisconnectingRef.current) {
      console.log(
        "[WebSocket] Skipping connect - already connecting or disconnecting",
      );
      return;
    }

    // Already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Already connecting - wait for it to complete
    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      // Let the existing connection attempt proceed
      return;
    }

    // Close existing connection before creating a new one
    if (wsRef.current) {
      console.log(
        "[WebSocket] Closing existing connection before reconnecting",
      );
      isDisconnectingRef.current = true;

      // Store the old WebSocket to close it
      const oldWs = wsRef.current;
      wsRef.current = null;

      // Close the old connection
      try {
        oldWs.close();
      } catch (e) {
        console.warn("[WebSocket] Error closing old connection:", e);
      }

      // Small delay to allow connection to close properly
      await new Promise((resolve) => setTimeout(resolve, 100));
      if (!isCurrent()) return;
      isDisconnectingRef.current = false;
    }

    isConnectingRef.current = true;

    try {
      const token = await getValidAccessToken();
      if (!isCurrent()) {
        return;
      }
      if (!token) {
        console.warn("[WebSocket] No auth token, skipping connection");
        return;
      }

      // Token sent after connection (more secure than URL query param)
      const wsUrl = buildWebSocketUrl("/ws");

      console.log("[WebSocket] Connecting to:", wsUrl);

      const ws = new WebSocket(wsUrl);

      // Send authentication after connection is established
      ws.onopen = () => {
        if (!isCurrent() || wsRef.current !== ws) return;
        console.log("[WebSocket] Connected, sending auth");
        ws.send(JSON.stringify({ type: "auth", token }));
        // Don't set isConnected yet — wait for auth:ok from server
      };

      ws.onmessage = (event) => {
        if (!isCurrent() || wsRef.current !== ws) return;
        try {
          const message = JSON.parse(event.data);

          if (message.type === "auth:ok") {
            // Auth confirmed by server — now truly connected
            isConnectingRef.current = false;
            setIsConnected(true);
            reconnectAttemptRef.current = 0;
            authFailureCountRef.current = 0;
            onWsOpenRef.current?.();
            console.log("[WebSocket] Auth confirmed");
            return;
          }

          console.log("[WebSocket] Received:", message);

          dispatchWebSocketMessage(message, {
            onSessionsRead: onSessionsReadRef.current,
            onTaskComplete: onTaskCompleteRef.current,
            onRecommendQuestions: onRecommendQuestionsRef.current,
            onUsageUpdated: onUsageUpdatedRef.current,
            onSandboxPresence: onSandboxPresenceRef.current,
            onSessionTaskStatus: onSessionTaskStatusRef.current,
          });
        } catch (e) {
          console.error("[WebSocket] Failed to parse message:", e);
        }
      };

      ws.onclose = (event) => {
        if (!isCurrent() || wsRef.current !== ws) return;
        console.log("[WebSocket] Disconnected:", event.code, event.reason);
        isConnectingRef.current = false;
        setIsConnected(false);
        onWsCloseRef.current?.();

        // Check if this was a manual disconnect BEFORE resetting the flag
        const wasManualDisconnect = isDisconnectingRef.current;
        isDisconnectingRef.current = false; // Reset here after socket is fully closed

        wsRef.current = null;

        // Don't reconnect on auth failure - token is invalid/expired
        // 4001: server explicitly rejects auth; reason may also indicate Unauthorized
        if (event.code === 4001 || event.reason === "Unauthorized") {
          if (getRefreshToken()) {
            void (async () => {
              try {
                await refreshAccessToken();
                if (!isCurrent()) return;
                authFailureCountRef.current = 0;
                if (isCurrent() && !wasManualDisconnect) {
                  connect();
                }
              } catch {
                if (!isCurrent()) return;
                // Don't redirect here — let authFetch / useAuth handle it.
                // A silent redirect from WebSocket background reconnection
                // is jarring; the user will get redirected on their next
                // intentional API call.
                console.warn(
                  "[WebSocket] Token refresh failed, will retry later",
                );
                authFailureCountRef.current++;
              }
            })();
            return;
          }
          authFailureCountRef.current++;
          if (authFailureCountRef.current >= MAX_AUTH_FAILURES) {
            // Switch to long-interval polling instead of permanently disabling
            console.warn(
              `[WebSocket] Auth failed ${
                authFailureCountRef.current
              } times, retrying in ${AUTH_FAILURE_COOLDOWN / 1000}s`,
            );
            if (enabled && !wasManualDisconnect) {
              reconnectTimeoutRef.current = setTimeout(() => {
                if (!isCurrent()) return;
                reconnectTimeoutRef.current = null;
                authFailureCountRef.current = 0; // Reset counter for the cooldown retry
                connect();
              }, AUTH_FAILURE_COOLDOWN);
            }
            return;
          }
          console.warn(
            `[WebSocket] Auth failed (${authFailureCountRef.current}/${MAX_AUTH_FAILURES}), will retry`,
          );
          // Fall through to normal reconnect with backoff
        } else {
          // Non-auth failure: reset auth failure counter
          authFailureCountRef.current = 0;
        }

        // Only attempt to reconnect if still enabled and not manually closed
        if (
          enabled &&
          reconnectTimeoutRef.current === null &&
          !wasManualDisconnect
        ) {
          // Calculate delay with exponential backoff
          const delay = Math.min(
            INITIAL_RECONNECT_DELAY *
              Math.pow(RECONNECT_DELAY_MULTIPLIER, reconnectAttemptRef.current),
            MAX_RECONNECT_DELAY,
          );
          reconnectAttemptRef.current++;

          console.log(
            `[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current})...`,
          );

          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isCurrent()) return;
            console.log("[WebSocket] Reconnecting...");
            reconnectTimeoutRef.current = null;
            connect();
          }, delay);
        }
      };

      ws.onerror = (error) => {
        if (!isCurrent() || wsRef.current !== ws) return;
        console.error("[WebSocket] Error:", error);
        isConnectingRef.current = false;
      };

      wsRef.current = ws;
    } catch (e) {
      if (!isCurrent()) return;
      console.error("[WebSocket] Connection failed:", e);
      isConnectingRef.current = false;
    }
  }, [enabled, scope]);

  const disconnect = useCallback(() => {
    connectionVersionRef.current += 1;
    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      const ws = wsRef.current;
      // Mark as disconnecting BEFORE closing to prevent reconnect attempts in onclose
      isDisconnectingRef.current = true;
      wsRef.current = null;
      ws.close();
    }
    isConnectingRef.current = false;
    setIsConnected(false);
    // Reset reconnect attempt counter on manual disconnect
    reconnectAttemptRef.current = 0;
    authFailureCountRef.current = 0;
    // Old callbacks are invalidated, so their delayed close cannot reset a new socket.
    isDisconnectingRef.current = false;
  }, []);

  // Store connect/disconnect in refs to avoid deps issues
  const connectRef = useRef(connect);
  const disconnectRef = useRef(disconnect);
  connectRef.current = connect;
  disconnectRef.current = disconnect;

  useEffect(() => {
    isMountedRef.current = true;
    if (enabled) {
      connectRef.current();
    } else {
      disconnectRef.current();
    }

    return () => {
      isMountedRef.current = false;
      disconnectRef.current();
    };
  }, [enabled, scope]);

  return {
    isConnected,
    connect,
    disconnect,
  };
}
