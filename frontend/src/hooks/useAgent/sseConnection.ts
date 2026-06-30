/**
 * SSE Connection utilities for useAgent hook
 * Handles SSE connection, reconnection, and stream management
 */

import { useCallback, useEffect } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { uuid } from "../../utils/uuid";
import { sessionApi } from "../../services/api";
import { buildApiUrl } from "../../services/api/config";
import {
  getValidAccessToken,
  refreshAccessToken,
} from "../../services/api/tokenManager";
import { getRefreshToken } from "../../services/api/token";
import type { EventType, StreamEvent } from "./types";
import { handleStreamEvent, type EventHandlerContext } from "./eventHandlers";
import { clearAllLoadingStates } from "./messageParts";
import type { Message, ConnectionStatus } from "../../types";

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

export type SSECloseAction = "terminal" | "retry";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isTerminalErrorPayload(data: unknown): boolean {
  if (!isRecord(data)) {
    return false;
  }

  return (
    typeof data.type === "string" ||
    typeof data.run_id === "string" ||
    typeof data.trace_id === "string"
  );
}

export function isTerminalSSEEvent(eventType: string, data?: unknown): boolean {
  if (eventType === "done" || eventType === "complete") {
    return true;
  }

  if (eventType === "error") {
    return isTerminalErrorPayload(data);
  }

  return false;
}

export function getSSECloseAction({
  receivedTerminalEvent,
}: {
  receivedTerminalEvent: boolean;
}): SSECloseAction {
  return receivedTerminalEvent ? "terminal" : "retry";
}

/**
 * Connect to SSE stream
 */
export async function connectToSSE(
  targetSessionId: string,
  targetRunId: string,
  messageId: string,
  ctx: SSEConnectionContext,
  hasRetried = false,
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

  const token = await getValidAccessToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  console.log(
    `[SSE] Connecting: session=${targetSessionId}, run_id=${targetRunId}`,
  );

  let receivedTerminalEvent = false;

  setConnectionStatus("connecting");
  retryCountRef.current = 0;

  try {
    await fetchEventSource(
      buildApiUrl(
        `/api/chat/sessions/${targetSessionId}/stream?run_id=${targetRunId}`,
      ),
      {
        headers,
        signal: abortControllerRef.current.signal,
        openWhenHidden: true,
        onopen: async (response) => {
          if (response.status === 401) {
            if (hasRetried) {
              // refreshAccessToken() in the first attempt already handled redirect
              // if needed, so just abort and throw
              throw new Error("SSE unauthorized after token refresh");
            }
            if (!getRefreshToken()) {
              throw new Error("SSE unauthorized: no refresh token");
            }
            try {
              await refreshAccessToken();
            } catch {
              throw new Error("SSE unauthorized: token refresh failed");
            }
            abortControllerRef.current?.abort();
            isConnectingRef.current = false;
            await connectToSSE(
              targetSessionId,
              targetRunId,
              messageId,
              ctx,
              true,
            );
            return;
          }
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          console.log("[SSE] Connection established");
          setConnectionStatus("connected");
          retryCountRef.current = 0;
        },
        onmessage: (event) => {
          if (event.event === "ping") return;
          const eventId = event.id || uuid();
          let parsedData: Record<string, unknown>;
          try {
            parsedData = JSON.parse(event.data);
          } catch {
            // Ignore parse errors
            return;
          }
          if (
            event.event === "error" &&
            !isTerminalSSEEvent(event.event, parsedData)
          ) {
            setConnectionStatus("reconnecting");
            throw new Error("SSE transport error before terminal event");
          }
          if (isTerminalSSEEvent(event.event, parsedData)) {
            receivedTerminalEvent = true;
          }
          const timestamp = parsedData._timestamp as string | undefined;
          const streamEvent: StreamEvent = {
            event: event.event as EventType,
            data: event.data,
          };
          handleStreamEvent(streamEvent, messageId, eventId, timestamp, ctx);
        },
        onerror: (err) => {
          console.error("[SSE] Connection error:", err);
          setConnectionStatus("reconnecting");
        },
        onclose: () => {
          console.log("[SSE] Connection closed");
          const closeAction = getSSECloseAction({ receivedTerminalEvent });
          if (closeAction === "retry") {
            setConnectionStatus("reconnecting");
            throw new Error("SSE closed before terminal event");
          }
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

/**
 * Options for the useSSEReconnect hook
 */
export interface SSEReconnectOptions {
  createSSEContext: () => SSEConnectionContext;
  sessionIdRef: React.MutableRefObject<string | null>;
  currentRunIdRef: React.MutableRefObject<string | null>;
  isReconnectFromHistoryRef: React.MutableRefObject<boolean>;
  streamingMessageIdRef: React.MutableRefObject<string | null>;
  connectionStatus: ConnectionStatus;
  setConnectionStatus: (status: ConnectionStatus) => void;
}

/**
 * Hook that manages SSE reconnection on visibility change and network events.
 * Returns a handleReconnectSSE function for manual use.
 */
export function useSSEReconnect(
  opts: SSEReconnectOptions,
): () => Promise<void> {
  const {
    createSSEContext,
    sessionIdRef,
    currentRunIdRef,
    isReconnectFromHistoryRef,
    streamingMessageIdRef,
    connectionStatus,
    setConnectionStatus,
  } = opts;

  const handleReconnectSSE = useCallback(async () => {
    const ctx = {
      ...createSSEContext(),
      sessionIdRef,
      currentRunIdRef,
      isReconnectFromHistoryRef,
    };
    await reconnectSSE(ctx);
  }, [
    createSSEContext,
    sessionIdRef,
    currentRunIdRef,
    isReconnectFromHistoryRef,
  ]);

  // Handle visibility change — reconnect when tab becomes visible
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
  }, [
    connectionStatus,
    handleReconnectSSE,
    sessionIdRef,
    currentRunIdRef,
    streamingMessageIdRef,
  ]);

  // Handle network status changes — reconnect on online, mark disconnected on offline
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
  }, [
    connectionStatus,
    handleReconnectSSE,
    sessionIdRef,
    currentRunIdRef,
    streamingMessageIdRef,
    setConnectionStatus,
  ]);

  return handleReconnectSSE;
}
