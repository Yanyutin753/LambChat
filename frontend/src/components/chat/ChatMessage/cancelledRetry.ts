import type { Message, MessageAttachment } from "../../../types";

export interface CancelledRetryTarget {
  userMessageId: string;
  assistantMessageId: string;
  content: string;
  attachments?: MessageAttachment[];
}

export function findCancelledRetryTarget(
  messages: Message[],
  assistantMessageId: string,
): CancelledRetryTarget | null {
  const assistantIndex = messages.findIndex(
    (message) => message.id === assistantMessageId,
  );
  if (assistantIndex <= 0) {
    return null;
  }

  for (let index = assistantIndex - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "user") {
      continue;
    }

    const content = message.content.trim();
    if (!content) {
      return null;
    }

    return {
      userMessageId: message.id,
      assistantMessageId,
      content,
      attachments: message.attachments,
    };
  }

  return null;
}
