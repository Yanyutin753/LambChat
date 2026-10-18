import type { Message } from "../../types";
import { reconstructMessagesFromEvents } from "./historyLoader";
import type { HistoryEvent } from "./types";

/** Use ordinary conversation replay for every public event, including active runs. */
export function replayScheduledEvents(
  events: HistoryEvent[],
  message: Message,
): Message {
  const replay = reconstructMessagesFromEvents(
    events
      .filter(
        (event) =>
          ![
            "scheduled:instruction",
            "user:message",
            "scheduled:result",
          ].includes(event.event_type),
      )
      .map((event) => ({
        ...event,
        run_id: event.run_id ?? message.runId,
        timestamp: event.timestamp ?? message.timestamp.toISOString(),
      })),
    new Set(),
    {
      activeSubagentStack: [],
      streaming: Boolean(
        message.isStreaming ||
          message.metadata?.scheduledProgressStatus === "waiting_human",
      ),
    },
  ).filter((item) => item.role === "assistant");
  return {
    ...message,
    parts: replay.flatMap((item) => item.parts ?? []),
    content: replay.map((item) => item.content).join(""),
    assistantIdentity:
      replay[0]?.assistantIdentity ?? message.assistantIdentity,
    tokenUsage: [...replay].reverse().find((item) => item.tokenUsage)
      ?.tokenUsage,
    duration: [...replay].reverse().find((item) => item.duration)?.duration,
    cancelled: replay.some((item) => item.cancelled),
  };
}
