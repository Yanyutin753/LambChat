import type { Message } from "../../types/message.ts";
import type { MessageAttachment } from "../../types/upload.ts";
import { uuid } from "../../utils/uuid.ts";

interface CreateOptimisticMessagesForSendOptions {
  previousMessages: Message[];
  content: string;
  attachments?: MessageAttachment[];
  enabledSkills?: string[];
  runModes?: Array<"auto" | "goal">;
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
  enabledSkills,
  runModes,
  now = new Date(),
  createId = () => uuid(),
}: CreateOptimisticMessagesForSendOptions): CreateOptimisticMessagesForSendResult {
  const userMessage: Message = {
    id: createId(),
    role: "user",
    content: content.trim(),
    timestamp: now,
    attachments,
    enabledSkills,
    runModes,
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
