import type {
  Message,
  MessagePart,
  SessionEventsResponse,
} from "../../../types";
import { reconstructMessagesFromEvents } from "../../../hooks/useAgent/historyLoader";

const MAX_NOTIFICATION_SUMMARY_LENGTH = 30;

export interface TaskNotificationCopy {
  title: string;
  body: string;
  statusLabel: string;
  isSuccess: boolean;
}

interface BuildTaskNotificationCopyInput {
  events?: SessionEventsResponse["events"];
  fallbackMessage?: string;
  failureLabel: string;
  sessionName?: string;
  successLabel: string;
  status: "completed" | "failed";
}

export function buildTaskNotificationCopy({
  events,
  fallbackMessage,
  failureLabel,
  sessionName,
  successLabel,
  status,
}: BuildTaskNotificationCopyInput): TaskNotificationCopy {
  const isSuccess = status === "completed";
  const statusLabel = isSuccess ? successLabel : failureLabel;
  const normalizedSessionName = normalizeText(sessionName);
  const assistantSummary = isSuccess ? getLatestAssistantSummary(events) : "";
  const fallbackSummary = normalizeText(fallbackMessage);
  const body = truncateText(
    assistantSummary || fallbackSummary || statusLabel,
    MAX_NOTIFICATION_SUMMARY_LENGTH,
  );

  return {
    title: normalizedSessionName || statusLabel,
    body,
    statusLabel,
    isSuccess,
  };
}

function getLatestAssistantSummary(
  events?: SessionEventsResponse["events"],
): string {
  if (!events?.length) {
    return "";
  }

  const messages = reconstructMessagesFromEvents(events, new Set(), {
    activeSubagentStack: [],
  });

  const lastAssistantMessage = [...messages]
    .reverse()
    .find((message) => message.role === "assistant");

  if (!lastAssistantMessage) {
    return "";
  }

  return normalizeText(extractAssistantText(lastAssistantMessage));
}

function extractAssistantText(message: Message): string {
  if (message.parts?.length) {
    const partsText = collectPartText(message.parts);
    if (partsText) {
      return partsText;
    }
  }

  return message.content || "";
}

function collectPartText(parts: MessagePart[]): string {
  const textParts: string[] = [];

  for (const part of parts) {
    if (part.type === "text" || part.type === "summary") {
      textParts.push(part.content);
      continue;
    }

    if (part.type === "subagent" && part.parts?.length) {
      const nestedText = collectPartText(part.parts);
      if (nestedText) {
        textParts.push(nestedText);
      }
    }
  }

  return textParts.join(" ");
}

function normalizeText(value?: string): string {
  return (value || "").replace(/\s+/g, " ").trim();
}

function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value
    .slice(0, maxLength - 1)
    .replace(/\s+\S*$/, "")
    .trim()}…`;
}
