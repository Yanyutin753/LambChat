/**
 * SSE Connection utilities for useAgent hook
 * Handles SSE connection, reconnection, and stream management
 */

import { fetchEventSource } from "@microsoft/fetch-event-source";
import { getAccessToken, sessionApi } from "../../services/api";
import type { EventType, StreamEvent } from "./types";
import { handleStreamEvent, type EventHandlerContext } from "./eventHandlers";
import { clearAllLoadingStates } from "./messageParts";

/**
 * SSE Connection context
 */
export interface SSEConnectionContext extends EventHandlerContext {
  abortControllerRef: React.MutableRefObject<AbortController | null>;
  isConnectingRef: React.MutableRefObject<boolean>;
  streamingMessageIdRef: React.MutableRefObject<string | null>;
  reconnectTimeoutRef: React.MutableRefObject<ReturnType<
    typeof setTimeout
  > | null>;
  retryCountRef: React.MutableRefObject<number>;
  messagesRef: React.MutableRefObject<Message[]>;
}

/**
 * Exponential backoff for reconnection
 */
export function getReconnectDelay(retryCount: number): number {
  const baseDelay = Math.min(Math.pow(2, retryCount), 30) * 1000;
  const jitter = Math.random() * 1000;
  return baseDelay + jitter;
}

/**
 * Clear reconnect timeout
 */
export function clearReconnectTimeout(
  reconnectTimeoutRef: React.MutableRefObject<ReturnType<
    typeof setTimeout
  > | null>,
): void {
  if (reconnectTimeoutRef.current) {
    clearTimeout(reconnectTimeoutRef.current);
    reconnectTimeoutRef.current = null;
  }
}

/**
 * Connect to SSE stream
 */
export async function connectToSSE(
  targetSessionId: string,
  targetRunId: string,
  messageId: string,
  ctx: SSEConnectionContext,
): Promise<void> {
  const {
    abortControllerRef,
    isConnectingRef,
    streamingMessageIdRef,
    setConnectionStatus,
    retryCountRef,
  } = ctx;

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
      `/api/chat/sessions/${targetSessionId}/stream?run_id=${targetRunId}`,
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
            handleStreamEvent(streamEvent, messageId, eventId, timestamp, ctx);
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
          ctx.setIsInitializingSandbox(false);
          ctx.setMessages((prev) =>
            prev.map((m) =>
              m.id === messageId
                ? {
                    ...m,
                    isStreaming: false,
                    parts: clearAllLoadingStates(m.parts || []),
                  }
                : m,
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
}

/**
 * Smart reconnect with exponential backoff
 */
export async function reconnectSSE(
  ctx: SSEConnectionContext & {
    sessionIdRef: React.MutableRefObject<string | null>;
    currentRunIdRef: React.MutableRefObject<string | null>;
    isReconnectFromHistoryRef: React.MutableRefObject<boolean>;
  },
): Promise<void> {
  const {
    sessionIdRef,
    currentRunIdRef,
    streamingMessageIdRef,
    abortControllerRef,
    isConnectingRef,
    reconnectTimeoutRef,
    retryCountRef,
    messagesRef,
    isReconnectFromHistoryRef,
    setConnectionStatus,
  } = ctx;

  const currentSessId = sessionIdRef.current;
  const currentRId = currentRunIdRef.current;
  const currentMsgId = streamingMessageIdRef.current;

  if (!currentSessId || !currentRId) {
    console.log("[SSE] No session/run ID, skipping reconnect");
    return;
  }

  clearReconnectTimeout(reconnectTimeoutRef);

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
      ctx.setIsInitializingSandbox(false);
      streamingMessageIdRef.current = null;
      // Clear loading states on the message
      if (currentMsgId) {
        ctx.setMessages((prev) =>
          prev.map((m) =>
            m.id === currentMsgId
              ? {
                  ...m,
                  isStreaming: false,
                  parts: clearAllLoadingStates(m.parts || []),
                }
              : m,
          ),
        );
      }
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
      const msgs = messagesRef.current;
      const lastMsg = msgs.find((m) => m.id === currentMsgId);
      if (lastMsg) {
        isReconnectFromHistoryRef.current = true;
        await connectToSSE(currentSessId, currentRId, currentMsgId, ctx);
      }
    }
  }, delay);
}

// Import Message type for messagesRef
import type { Message } from "../../types";
