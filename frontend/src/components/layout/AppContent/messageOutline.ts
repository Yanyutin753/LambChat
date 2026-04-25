import type { Message, MessagePart } from "../../../types";

export type MessageOutlineItem =
  | {
      id: string;
      anchorId: string;
      kind: "user-message";
      label: string;
      level: 1;
      messageId: string;
      messageIndex: number;
    }
  | {
      id: string;
      anchorId: string;
      kind: "assistant-message";
      label: string;
      level: 1;
      messageId: string;
      messageIndex: number;
    }
  | {
      id: string;
      anchorId: string;
      kind: "assistant-heading";
      label: string;
      level: 1 | 2 | 3;
      messageId: string;
      messageIndex: number;
    };

const USER_MESSAGE_THRESHOLD = 0;
const USER_SUMMARY_MAX_LENGTH = 25;
const ASSISTANT_SUMMARY_MAX_LENGTH = 40;
const HEADING_PATTERN = /^(?: {0,3})(#{1,3})[ \t]+(.+?)\s*#*\s*$/gm;
const FENCED_CODE_BLOCK_PATTERN = /```[\s\S]*?```/g;

export function slugifyHeadingText(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s\u4e00-\u9fff-]/g, "")
    .replace(/[\s]+/g, "-");
}

export function createMessageAnchorId(messageId: string): string {
  return `chat-outline-message-${messageId}`;
}

export function createHeadingAnchorId({
  messageId,
  partIndex,
  headingText,
}: {
  messageId: string;
  partIndex: number;
  headingText: string;
}): string {
  return `chat-outline-heading-${messageId}-${partIndex}-${slugifyHeadingText(
    headingText,
  )}`;
}

export function shouldShowMessageOutline(messages: Message[]): boolean {
  let userMessageCount = 0;

  for (const message of messages) {
    if (message.role === "user") {
      userMessageCount += 1;
      if (userMessageCount > USER_MESSAGE_THRESHOLD) {
        return true;
      }
    }
  }

  return false;
}

export function extractMessageOutline(
  messages: Message[],
): MessageOutlineItem[] {
  const outline: MessageOutlineItem[] = [];

  messages.forEach((message, messageIndex) => {
    if (message.role === "user") {
      const label = summarizeUserMessage(message);
      if (!label) return;

      outline.push({
        id: `message:${message.id}`,
        anchorId: createMessageAnchorId(message.id),
        kind: "user-message",
        label,
        level: 1,
        messageId: message.id,
        messageIndex,
      });
      return;
    }

    if (message.role !== "assistant") {
      return;
    }

    const label = summarizeAssistantMessage(message);
    if (label) {
      outline.push({
        id: `assistant:${message.id}`,
        anchorId: createMessageAnchorId(message.id),
        kind: "assistant-message",
        label,
        level: 1,
        messageId: message.id,
        messageIndex,
      });
    }

    getAssistantTextBlocks(message).forEach(({ content, partIndex }) => {
      extractMarkdownHeadings(content).forEach(({ level, text }) => {
        outline.push({
          id: `heading:${message.id}:${partIndex}:${text}`,
          anchorId: createHeadingAnchorId({
            messageId: message.id,
            partIndex,
            headingText: text,
          }),
          kind: "assistant-heading",
          label: text,
          level,
          messageId: message.id,
          messageIndex,
        });
      });
    });
  });

  return outline;
}

function summarizeUserMessage(message: Message): string {
  const firstLine = resolveUserMessageText(message)
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean);

  if (!firstLine) {
    return "";
  }

  if (firstLine.length <= USER_SUMMARY_MAX_LENGTH) {
    return firstLine;
  }

  return `${firstLine.slice(0, USER_SUMMARY_MAX_LENGTH - 1)}…`;
}

function summarizeAssistantMessage(message: Message): string {
  const text = getAssistantTextBlocks(message)
    .map((b) => b.content)
    .join("\n");

  const cleaned = text
    .replace(FENCED_CODE_BLOCK_PATTERN, "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)[0];

  if (!cleaned) return "";

  if (cleaned.length <= ASSISTANT_SUMMARY_MAX_LENGTH) return cleaned;
  return `${cleaned.slice(0, ASSISTANT_SUMMARY_MAX_LENGTH - 1)}…`;
}

function resolveUserMessageText(message: Message): string {
  const textParts =
    message.parts?.filter(
      (part): part is Extract<MessagePart, { type: "text" }> =>
        part.type === "text",
    ) ?? [];

  if (textParts.length > 0) {
    return textParts.map((part) => part.content).join("\n");
  }

  return message.content ?? "";
}

function getAssistantTextBlocks(
  message: Message,
): Array<{ content: string; partIndex: number }> {
  const textParts =
    message.parts?.flatMap((part, partIndex) =>
      part.type === "text" ? [{ content: part.content, partIndex }] : [],
    ) ?? [];

  if (textParts.length > 0) {
    return textParts;
  }

  return message.content ? [{ content: message.content, partIndex: 0 }] : [];
}

function extractMarkdownHeadings(
  content: string,
): Array<{ level: 1 | 2 | 3; text: string }> {
  const headings: Array<{ level: 1 | 2 | 3; text: string }> = [];
  const normalizedContent = content.replace(FENCED_CODE_BLOCK_PATTERN, "");

  for (const match of normalizedContent.matchAll(HEADING_PATTERN)) {
    const [, hashes, rawText] = match;
    const level = hashes.length as 1 | 2 | 3;
    const text = rawText.trim();

    if (!text) {
      continue;
    }

    headings.push({ level, text });
  }

  return headings;
}
