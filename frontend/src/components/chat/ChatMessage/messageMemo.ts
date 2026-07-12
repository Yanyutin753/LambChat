import type { Message } from "../../../types";
import type { MessagePart } from "../../../types";
import type { AutoPreviewTarget } from "./autoPreviewEligibility";
import type { RevealPreviewRequest } from "./items/revealPreviewData";

export interface ChatMessageMemoProps {
  message: Message;
  sessionId?: string;
  runId?: string;
  isLastMessage?: boolean;
  personaAvatar?: string | null;
  personaName?: string | null;
  activePreview?: RevealPreviewRequest | null;
  latestAutoPreview?: AutoPreviewTarget | null;
  onOpenPreview?: unknown;
  onForkMessage?: unknown;
  onRecommendQuestionClick?: unknown;
  onRetryCancelledMessage?: unknown;
  showFeedbackAndShareActions?: boolean;
  activeGoal?: unknown;
  isFirst?: boolean;
}

function getPreviewKey(preview?: RevealPreviewRequest | null): string {
  if (!preview) return "";
  return `${preview.kind}:${preview.previewKey}`;
}

function partOwnsPreview(part: MessagePart, previewKey: string): boolean {
  if (part.type === "artifact") {
    return part.artifact.preview?.previewKey === previewKey;
  }
  if (part.type === "subagent") {
    return (
      part.parts?.some((nested) => partOwnsPreview(nested, previewKey)) ?? false
    );
  }
  return false;
}

function messageOwnsPreview(
  message: Message,
  preview?: RevealPreviewRequest | null,
): boolean {
  if (!preview || !message.parts?.length) return false;
  return message.parts.some((part) =>
    partOwnsPreview(part, preview.previewKey),
  );
}

function getAutoPreviewKey(preview?: AutoPreviewTarget | null): string {
  if (!preview) return "";
  return `${preview.messageId}:${preview.partIndex}`;
}

function isAutoPreviewRelevant(
  messageId: string,
  preview?: AutoPreviewTarget | null,
): boolean {
  return preview?.messageId === messageId;
}

export function areChatMessagePropsEqual(
  prev: ChatMessageMemoProps,
  next: ChatMessageMemoProps,
): boolean {
  const prevMessageId = prev.message.id;
  const nextMessageId = next.message.id;
  if (prevMessageId !== nextMessageId) return false;
  if (prev.message !== next.message) return false;
  if (prev.isLastMessage !== next.isLastMessage) return false;
  if (prev.isFirst !== next.isFirst) return false;
  if (prev.sessionId !== next.sessionId) return false;
  if (prev.runId !== next.runId) return false;
  if (prev.personaAvatar !== next.personaAvatar) return false;
  if (prev.personaName !== next.personaName) return false;
  if (prev.showFeedbackAndShareActions !== next.showFeedbackAndShareActions) {
    return false;
  }
  if (prev.activeGoal !== next.activeGoal) return false;
  if (prev.onOpenPreview !== next.onOpenPreview) return false;
  if (prev.onForkMessage !== next.onForkMessage) return false;
  if (prev.onRecommendQuestionClick !== next.onRecommendQuestionClick) {
    return false;
  }
  if (prev.onRetryCancelledMessage !== next.onRetryCancelledMessage) {
    return false;
  }

  const prevAutoRelevant = isAutoPreviewRelevant(
    prevMessageId,
    prev.latestAutoPreview,
  );
  const nextAutoRelevant = isAutoPreviewRelevant(
    nextMessageId,
    next.latestAutoPreview,
  );
  if (prevAutoRelevant || nextAutoRelevant) {
    return (
      getAutoPreviewKey(prev.latestAutoPreview) ===
      getAutoPreviewKey(next.latestAutoPreview)
    );
  }

  const prevPreviewRelevant = messageOwnsPreview(
    prev.message,
    prev.activePreview,
  );
  const nextPreviewRelevant = messageOwnsPreview(
    next.message,
    next.activePreview,
  );
  if (prevPreviewRelevant || nextPreviewRelevant) {
    return (
      getPreviewKey(prev.activePreview) === getPreviewKey(next.activePreview)
    );
  }

  return true;
}
