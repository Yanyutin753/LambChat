import type { MessagePart } from "../../../types";

interface AutoPreviewMessageLike {
  id: string;
  isStreaming?: boolean;
  parts?: MessagePart[];
}

export interface AutoPreviewTarget {
  messageId: string;
  partIndex: number;
}

function isAutoPreviewToolPart(part: MessagePart): boolean {
  return (
    part.type === "tool" &&
    part.success === true &&
    !part.isPending &&
    !part.cancelled &&
    (part.name === "reveal_file" || part.name === "reveal_project")
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
