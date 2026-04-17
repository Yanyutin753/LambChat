import type { MessagePart } from "../../../types";

function isAutoPreviewToolPart(part: MessagePart): boolean {
  return (
    part.type === "tool" &&
    (part.name === "reveal_file" || part.name === "reveal_project")
  );
}

export function getLastAutoPreviewPartIndex(
  parts: MessagePart[] | undefined,
): number {
  if (!parts?.length) {
    return -1;
  }

  for (let index = parts.length - 1; index >= 0; index -= 1) {
    if (isAutoPreviewToolPart(parts[index])) {
      return index;
    }
  }

  return -1;
}

export function shouldAllowAutoPreviewForPart(input: {
  isLastMessage?: boolean;
  isMessageStreaming?: boolean;
  partIndex: number;
  lastAutoPreviewPartIndex: number;
}): boolean {
  return (
    !!input.isLastMessage &&
    !input.isMessageStreaming &&
    input.lastAutoPreviewPartIndex >= 0 &&
    input.partIndex === input.lastAutoPreviewPartIndex
  );
}
