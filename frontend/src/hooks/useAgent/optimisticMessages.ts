import type { Message } from "../../types/message.ts";
import type { MessageAttachment } from "../../types/upload.ts";
import { uuid } from "../../utils/uuid.ts";

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

interface CreateOptimisticMessagesForRetryOptions {
  previousMessages: Message[];
  assistantMessageId?: string;
  afterUserMessageId?: string;
  now?: Date;
  createId?: () => string;
}

function createStreamingAssistantMessage(
  now: Date,
  createId: () => string,
): Message {
  return {
    id: createId(),
    role: "assistant",
    content: "",
    timestamp: now,
    toolCalls: [],
    toolResults: [],
    isStreaming: true,
  };
}

export function createOptimisticMessagesForSend({
  previousMessages,
  content,
  attachments,
  now = new Date(),
  createId = () => uuid(),
}: CreateOptimisticMessagesForSendOptions): CreateOptimisticMessagesForSendResult {
  const userMessage: Message = {
    id: createId(),
    role: "user",
    content: content.trim(),
    timestamp: now,
    attachments,
  };

  const assistantMessage: Message = {
    ...createStreamingAssistantMessage(now, createId),
  };

  return {
    messages: [...previousMessages, userMessage, assistantMessage],
    assistantMessageId: assistantMessage.id,
  };
}

export function createOptimisticMessagesForRetry({
  previousMessages,
  assistantMessageId,
  afterUserMessageId,
  now = new Date(),
  createId = () => uuid(),
}: CreateOptimisticMessagesForRetryOptions): CreateOptimisticMessagesForSendResult {
  const assistantMessage = createStreamingAssistantMessage(now, createId);
  const existingAssistantIndex = assistantMessageId
    ? previousMessages.findIndex((message) => message.id === assistantMessageId)
    : -1;

  if (existingAssistantIndex !== -1) {
    const messages = [...previousMessages];
    messages[existingAssistantIndex] = assistantMessage;
    return { messages, assistantMessageId: assistantMessage.id };
  }

  const userMessageIndex = afterUserMessageId
    ? previousMessages.findIndex((message) => message.id === afterUserMessageId)
    : -1;
  if (userMessageIndex !== -1) {
    const messages = [...previousMessages];
    messages.splice(userMessageIndex + 1, 0, assistantMessage);
    return { messages, assistantMessageId: assistantMessage.id };
  }

  return {
    messages: [...previousMessages, assistantMessage],
    assistantMessageId: assistantMessage.id,
  };
}
