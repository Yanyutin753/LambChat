import { useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Message } from "../../types";
import type { UseAgentOptions } from "./types";
import { sessionApi } from "../../services/api/session";
import {
  isScheduledProgress,
  mergeScheduledProgress,
  SCHEDULED_PROGRESS_EVENT,
  isScheduledResult,
  mergeScheduledResult,
  SCHEDULED_RESULT_EVENT,
  SCHEDULED_RESULTS_REFRESH_EVENT,
} from "./scheduledResults";

export function useScheduledResults(
  sessionId: string | null,
  userId: string | undefined,
  setMessages: Dispatch<SetStateAction<Message[]>>,
  messages: Message[],
  onQuiet?: (sessionId: string, messageId: string, userId: string) => void,
  callbacks?: Pick<
    UseAgentOptions,
    "onApprovalRequired" | "onApprovalResolved"
  >,
) {
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;
  useEffect(() => {
    if (!sessionId || !userId) return;
    const controller = new AbortController();
    const hydrate = async () => {
      for (const message of messages) {
        if (controller.signal.aborted) return;
        const runId = message.runId;
        const source = message.metadata?.scheduledExecutionSessionId;
        const taskId = message.metadata?.scheduledTaskId;
        const taskName = message.metadata?.scheduledTaskName;
        if (
          !message.metadata?.scheduledFinal ||
          message.metadata.scheduledEventsLoaded ||
          typeof source !== "string" ||
          !runId ||
          typeof taskId !== "string" ||
          typeof taskName !== "string"
        )
          continue;
        try {
          const response = await sessionApi.getEvents(source, {
            run_id: runId,
            signal: controller.signal,
          });
          if (controller.signal.aborted) return;
          setMessages((previous) =>
            controller.signal.aborted
              ? previous
              : mergeScheduledResult(previous, {
                  session_id: sessionId,
                  run_id: runId,
                  message_id: message.id,
                  task_id: taskId,
                  task_name: taskName,
                  content: message.content,
                  timestamp: message.timestamp.toISOString(),
                  execution_session_id: source,
                  events: response.events,
                }),
          );
        } catch (error) {
          if (!controller.signal.aborted)
            console.warn("Scheduled execution history deferred", error);
        }
      }
    };
    void hydrate();
    return () => controller.abort();
  }, [messages, sessionId, userId, setMessages]);

  useEffect(() => {
    if (!sessionId || !userId) return;
    const controller = new AbortController();
    const settledIds = new Set<string>();
    const fetchingProgress = new Set<string>();
    const restoreProgress = async (
      data: import("./scheduledResults").ScheduledProgress,
    ) => {
      if (!data.execution_session_id || fetchingProgress.has(data.message_id))
        return;
      fetchingProgress.add(data.message_id);
      try {
        const response = await sessionApi.getEvents(data.execution_session_id, {
          run_id: data.run_id,
          include_active_events: true,
          signal: controller.signal,
        });
        if (!controller.signal.aborted && !settledIds.has(data.message_id)) {
          setMessages((previous) =>
            controller.signal.aborted
              ? previous
              : mergeScheduledProgress(previous, {
                  ...data,
                  events: response.events,
                }),
          );
        }
      } catch (error) {
        if (!controller.signal.aborted)
          console.warn("Scheduled execution progress deferred", error);
      } finally {
        fetchingProgress.delete(data.message_id);
      }
    };
    const applyProgress = (data: unknown) => {
      if (
        !isScheduledProgress(data) ||
        data.session_id !== sessionId ||
        settledIds.has(data.message_id)
      )
        return;
      for (const approval of data.approvals ?? []) {
        callbacksRef.current?.onApprovalRequired?.(approval);
      }
      for (const event of data.events ?? []) {
        const payload = event.data as { id?: string };
        if (event.event_type === "approval_resolved" && payload.id) {
          callbacksRef.current?.onApprovalResolved?.(payload.id);
        }
      }
      if (data.events_omitted) void restoreProgress(data);
      if (data.status === "quiet") {
        settledIds.add(data.message_id);
        onQuiet?.(sessionId, data.message_id, userId);
      }
      setMessages((previous) =>
        controller.signal.aborted
          ? previous
          : mergeScheduledProgress(previous, data),
      );
    };
    const receiveProgress = (event: Event) =>
      applyProgress((event as CustomEvent).detail);
    const receive = (event: Event) => {
      const data: unknown = (event as CustomEvent).detail;
      if (isScheduledResult(data) && data.session_id === sessionId) {
        settledIds.add(data.message_id);
        setMessages((previous) =>
          controller.signal.aborted
            ? previous
            : mergeScheduledResult(previous, data),
        );
      }
    };
    let inFlight = false;
    const refresh = async () => {
      if (inFlight || document.visibilityState === "hidden") return;
      inFlight = true;
      try {
        const response = await sessionApi.getEvents(sessionId, {
          event_types: ["scheduled:result"],
          trace_limit: 50,
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          for (const event of response.events) {
            if (isScheduledResult(event.data))
              settledIds.add(event.data.message_id);
          }
          setMessages((previous) =>
            controller.signal.aborted
              ? previous
              : response.events.reduce(
                  (messages, event) =>
                    isScheduledResult(event.data)
                      ? mergeScheduledResult(messages, event.data)
                      : messages,
                  previous,
                ),
          );
          const runIds = [
            ...new Set(
              messagesRef.current.flatMap((message) =>
                message.metadata?.scheduledTaskId &&
                !message.metadata.scheduledFinal &&
                message.metadata.scheduledProgressStatus !== "failed" &&
                message.runId
                  ? [message.runId]
                  : [],
              ),
            ),
          ];
          for (
            let offset = 0;
            offset < Math.max(runIds.length, 1);
            offset += 100
          ) {
            const active = await sessionApi.getScheduledProgress(
              sessionId,
              controller.signal,
              runIds.slice(offset, offset + 100),
            );
            if (controller.signal.aborted) return;
            active.progress.forEach(applyProgress);
          }
        }
      } catch (error) {
        if (!controller.signal.aborted)
          console.warn("Scheduled result catch-up deferred", error);
      } finally {
        inFlight = false;
      }
    };
    void refresh();
    const catchUpTimer = window.setInterval(refresh, 30_000);
    window.addEventListener(SCHEDULED_PROGRESS_EVENT, receiveProgress);
    window.addEventListener(SCHEDULED_RESULT_EVENT, receive);
    window.addEventListener(SCHEDULED_RESULTS_REFRESH_EVENT, refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      controller.abort();
      window.clearInterval(catchUpTimer);
      window.removeEventListener(SCHEDULED_PROGRESS_EVENT, receiveProgress);
      window.removeEventListener(SCHEDULED_RESULT_EVENT, receive);
      window.removeEventListener(SCHEDULED_RESULTS_REFRESH_EVENT, refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [sessionId, userId, setMessages, onQuiet]);
}
