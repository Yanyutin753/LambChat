import type { Message } from "../../types";
import { processMessageEvent } from "./eventProcessor";

export function applyRecommendQuestionsToMessages(
  messages: Message[],
  runId: string,
  questions: string[],
): Message[] {
  const normalized = questions
    .filter((question): question is string => typeof question === "string")
    .map((question) => question.trim())
    .filter(Boolean)
    .slice(0, 3);
  if (!runId || normalized.length === 0) return messages;

  let changed = false;
  const updated = messages.map((message) => {
    if (
      message.role !== "assistant" ||
      (message.runId !== runId && message.id !== runId)
    ) {
      return message;
    }

    const result = processMessageEvent(
      "recommend:questions",
      { questions: normalized },
      message.parts || [],
      message.content,
      message.toolCalls || [],
      0,
      [],
      Boolean(message.isStreaming),
      message.id,
    );
    changed = true;
    return {
      ...message,
      parts: result.parts,
      content: result.content,
      toolCalls: result.toolCalls,
    };
  });

  return changed ? updated : messages;
}
