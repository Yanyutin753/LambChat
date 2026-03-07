import { useEffect, useRef, useCallback, useState } from "react";
import { getAccessToken } from "../services/api";

export interface TaskCompleteNotification {
  type: "task:complete";
  data: {
    session_id: string;
    run_id: string;
    status: "completed" | "failed";
    message?: string;
  };
}

type WebSocketMessage = TaskCompleteNotification;

interface UseWebSocketOptions {
  onTaskComplete?: (notification: TaskCompleteNotification) => void;
  enabled?: boolean;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { onTaskComplete, enabled = true } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const onTaskCompleteRef = useRef(onTaskComplete);
  const [isConnected, setIsConnected] = useState(false);

  // Track connection state to prevent race conditions
  const isConnectingRef = useRef(false);
  const isDisconnectingRef = useRef(false);

  // Update ref when callback changes
  useEffect(() => {
    onTaskCompleteRef.current = onTaskComplete;
  }, [onTaskComplete]);

  const connect = useCallback(async () => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current || isDisconnectingRef.current) {
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
      const token = await getAccessToken();
      if (!token) {
        console.warn("[WebSocket] No auth token, skipping connection");
        return;
      }

      // Determine WebSocket URL based on current location
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      // Pass token as query parameter for authentication
      const wsUrl = `${protocol}//${host}/ws?token=${encodeURIComponent(
        token,
      )}`;

      console.log("[WebSocket] Connecting to:", wsUrl);

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log("[WebSocket] Connected");
        isConnectingRef.current = false;
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          console.log("[WebSocket] Received:", message);

          if (message.type === "task:complete" && onTaskCompleteRef.current) {
            onTaskCompleteRef.current(message);
          }
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

        // Only attempt to reconnect if still enabled and not manually closed
        if (
          enabled &&
          reconnectTimeoutRef.current === null &&
          !wasManualDisconnect
        ) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log("[WebSocket] Reconnecting...");
            reconnectTimeoutRef.current = null;
            connect();
          }, 3000);
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
    // NOTE: Don't reset isDisconnectingRef here - let the onclose handler do it
    // This prevents race conditions where connect() is called before the socket finishes closing
  }, []);

  // Store connect/disconnect in refs to avoid deps issues
  const connectRef = useRef(connect);
  const disconnectRef = useRef(disconnect);
  connectRef.current = connect;
  disconnectRef.current = disconnect;

  useEffect(() => {
    if (enabled) {
      connectRef.current();
    } else {
      disconnectRef.current();
    }

    return () => {
      disconnectRef.current();
    };
  }, [enabled]);

  return {
    isConnected,
    connect,
    disconnect,
  };
}
