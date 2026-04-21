import type { Message } from "../../types/message.ts";
import type { MessageAttachment } from "../../types/upload.ts";

interface CreateOptimisticMessagesForSendOptions {
  previousMessages: Message[];
  content: string;
  attachments?: MessageAttachment[];
  now?: Date;
  createId?: () => string;
}

interface CreateOptimisticMessagesForSendResult {
  messages: Message[];
  assistantMessageId: string;
}

export function createOptimisticMessagesForSend({
  previousMessages,
  content,
  attachments,
  now = new Date(),
  createId = () => crypto.randomUUID(),
}: CreateOptimisticMessagesForSendOptions): CreateOptimisticMessagesForSendResult {
  const userMessage: Message = {
    id: createId(),
    role: "user",
    content: content.trim(),
    timestamp: now,
    attachments,
  };

  const assistantMessage: Message = {
    id: createId(),
    role: "assistant",
    content: "",
    timestamp: now,
    toolCalls: [],
    toolResults: [],
    isStreaming: true,
  };

  return {
    messages: [...previousMessages, userMessage, assistantMessage],
    assistantMessageId: assistantMessage.id,
  };
}
