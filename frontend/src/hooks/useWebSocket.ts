import { useEffect, useRef, useCallback, useState } from "react";
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
    status: "completed" | "failed";
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

export interface WebSocketMessageHandlers {
  onTaskComplete?: (notification: TaskCompleteNotification) => void;
  onRecommendQuestions?: (notification: RecommendQuestionsNotification) => void;
  onSessionTaskStatus?: (data: {
    session_id: string;
    task_status: string;
  }) => void;
}

interface UseWebSocketOptions extends WebSocketMessageHandlers {
  enabled?: boolean;
}

export function dispatchWebSocketMessage(
  message: unknown,
  handlers: WebSocketMessageHandlers,
): void {
  if (!message || typeof message !== "object" || !("type" in message)) return;
  const typedMessage = message as { type?: unknown };
  if (typedMessage.type === "task:complete") {
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
    onRecommendQuestions,
    onSessionTaskStatus,
    enabled = true,
  } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const onTaskCompleteRef = useRef(onTaskComplete);
  const onRecommendQuestionsRef = useRef(onRecommendQuestions);
  const onSessionTaskStatusRef = useRef(onSessionTaskStatus);
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
    onSessionTaskStatusRef.current = onSessionTaskStatus;
  }, [onSessionTaskStatus]);

  const connect = useCallback(async () => {
    // Prevent multiple simultaneous connection attempts
    if (
      !isMountedRef.current ||
      isConnectingRef.current ||
      isDisconnectingRef.current
    ) {
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

      isDisconnectingRef.current = false;
    }

    isConnectingRef.current = true;

    try {
      const token = await getValidAccessToken();
      if (!isMountedRef.current) {
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
        console.log("[WebSocket] Connected, sending auth");
        ws.send(JSON.stringify({ type: "auth", token }));
        // Don't set isConnected yet — wait for auth:ok from server
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          if (message.type === "auth:ok") {
            // Auth confirmed by server — now truly connected
            isConnectingRef.current = false;
            setIsConnected(true);
            reconnectAttemptRef.current = 0;
            authFailureCountRef.current = 0;
            console.log("[WebSocket] Auth confirmed");
            return;
          }

          console.log("[WebSocket] Received:", message);

          dispatchWebSocketMessage(message, {
            onTaskComplete: onTaskCompleteRef.current,
            onRecommendQuestions: onRecommendQuestionsRef.current,
            onSessionTaskStatus: onSessionTaskStatusRef.current,
          });
        } catch (e) {
          console.error("[WebSocket] Failed to parse message:", e);
        }
      };

      ws.onclose = (event) => {
        console.log("[WebSocket] Disconnected:", event.code, event.reason);
        isConnectingRef.current = false;
        setIsConnected(false);

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
                authFailureCountRef.current = 0;
                if (isMountedRef.current && enabled && !wasManualDisconnect) {
                  connect();
                }
              } catch {
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
                reconnectTimeoutRef.current = null;
                authFailureCountRef.current = 0; // Reset counter for the cooldown retry
                if (!isMountedRef.current) {
                  return;
                }
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
            console.log("[WebSocket] Reconnecting...");
            reconnectTimeoutRef.current = null;
            if (!isMountedRef.current) {
              return;
            }
            connect();
          }, delay);
        }
      };

      ws.onerror = (error) => {
        console.error("[WebSocket] Error:", error);
        isConnectingRef.current = false;
      };

      wsRef.current = ws;
    } catch (e) {
      console.error("[WebSocket] Connection failed:", e);
      isConnectingRef.current = false;
    }
  }, [enabled]);

  const disconnect = useCallback(() => {
    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      const ws = wsRef.current;
      // Mark as disconnecting BEFORE closing to prevent reconnect attempts in onclose
      isDisconnectingRef.current = true;
      ws.close();
      wsRef.current = null;
    }
    isConnectingRef.current = false;
    setIsConnected(false);
    // Reset reconnect attempt counter on manual disconnect
    reconnectAttemptRef.current = 0;
    authFailureCountRef.current = 0;
    // NOTE: Don't reset isDisconnectingRef here - let the onclose handler do it
    // This prevents race conditions where connect() is called before the socket finishes closing
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
  }, [enabled]);

  return {
    isConnected,
    connect,
    disconnect,
  };
}
