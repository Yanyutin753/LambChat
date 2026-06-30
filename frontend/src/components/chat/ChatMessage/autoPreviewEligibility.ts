import type { MessagePart } from "../../../types";
import { collectRevealArtifacts } from "./revealArtifacts";
import type { RevealPreviewRequest } from "./items/revealPreviewData";

interface AutoPreviewMessageLike {
  id: string;
  runId?: string;
  isStreaming?: boolean;
  parts?: MessagePart[];
}

export interface AutoPreviewTarget {
  messageId: string;
  partIndex: number;
}

function isAutoPreviewToolPart(part: MessagePart): boolean {
  if (part.type === "artifact") {
    return part.success === true;
  }

  return (
    part.type === "tool" &&
    part.success === true &&
    !part.isPending &&
    !part.cancelled &&
    (part.name === "reveal_file" || part.name === "reveal_project")
  );
}

function isEligibleObservedCompletionMessage(input: {
  message: AutoPreviewMessageLike;
  observedStreamingMessageIds: ReadonlySet<string>;
  currentRunId?: string | null;
  allowHistoricalLatest?: boolean;
}): boolean {
  const {
    message,
    observedStreamingMessageIds,
    currentRunId,
    allowHistoricalLatest,
  } = input;
  const isCurrentRunMessage = !!currentRunId && message.runId === currentRunId;
  return (
    !message.isStreaming &&
    !!message.parts?.length &&
    (allowHistoricalLatest ||
      observedStreamingMessageIds.has(message.id) ||
      isCurrentRunMessage)
  );
}

export function getLatestAutoPreviewTarget(
  messages: AutoPreviewMessageLike[],
): AutoPreviewTarget | null {
  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = messages[messageIndex];
    if (message.isStreaming || !message.parts?.length) {
      continue;
    }

    for (
      let partIndex = message.parts.length - 1;
      partIndex >= 0;
      partIndex -= 1
    ) {
      if (isAutoPreviewToolPart(message.parts[partIndex])) {
        return {
          messageId: message.id,
          partIndex,
        };
      }
    }
  }

  return null;
}

export function getLatestChatAutoPreviewTarget(input: {
  messages: AutoPreviewMessageLike[];
  suppressAutoPreview?: boolean;
}): AutoPreviewTarget | null {
  if (input.suppressAutoPreview) {
    return null;
  }

  return getLatestAutoPreviewTarget(input.messages);
}

export function getLatestObservedCompletionAutoPreviewTarget(input: {
  messages: AutoPreviewMessageLike[];
  observedStreamingMessageIds: ReadonlySet<string>;
  suppressAutoPreview?: boolean;
  currentRunId?: string | null;
}): AutoPreviewTarget | null {
  if (input.suppressAutoPreview) {
    return null;
  }

  for (
    let messageIndex = input.messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = input.messages[messageIndex];
    if (
      !isEligibleObservedCompletionMessage({
        message,
        observedStreamingMessageIds: input.observedStreamingMessageIds,
        currentRunId: input.currentRunId,
      })
    ) {
      continue;
    }

    const parts = message.parts;
    if (!parts?.length) {
      continue;
    }

    for (let partIndex = parts.length - 1; partIndex >= 0; partIndex -= 1) {
      if (isAutoPreviewToolPart(parts[partIndex])) {
        return {
          messageId: message.id,
          partIndex,
        };
      }
    }
  }

  return null;
}

export function getLatestObservedCompletionRevealPreviewRequest(input: {
  messages: AutoPreviewMessageLike[];
  observedStreamingMessageIds: ReadonlySet<string>;
  suppressAutoPreview?: boolean;
  currentRunId?: string | null;
  allowHistoricalLatest?: boolean;
}): RevealPreviewRequest | null {
  if (input.suppressAutoPreview) {
    return null;
  }

  for (
    let messageIndex = input.messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = input.messages[messageIndex];
    if (
      !isEligibleObservedCompletionMessage({
        message,
        observedStreamingMessageIds: input.observedStreamingMessageIds,
        currentRunId: input.currentRunId,
        allowHistoricalLatest: input.allowHistoricalLatest,
      })
    ) {
      continue;
    }

    const artifacts = collectRevealArtifacts(message.parts);
    for (
      let artifactIndex = artifacts.length - 1;
      artifactIndex >= 0;
      artifactIndex -= 1
    ) {
      const artifact = artifacts[artifactIndex];
      return artifact.preview;
    }
  }

  return null;
}

export function shouldAllowAutoPreviewForPart(input: {
  messageId: string;
  partIndex: number;
  latestAutoPreview: AutoPreviewTarget | null;
}): boolean {
  return (
    !!input.latestAutoPreview &&
    input.latestAutoPreview.messageId === input.messageId &&
    input.latestAutoPreview.partIndex === input.partIndex
  );
}
