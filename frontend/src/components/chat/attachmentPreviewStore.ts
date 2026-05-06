import type { MessageAttachment } from "../../types";
import { createSingletonStore } from "./ChatMessage/items/createSingletonStore";
import {
  registerPanelCapture,
  pushCurrentPanelToHistory,
} from "./ChatMessage/items/sidebarHistoryStore";

export type AttachmentPreviewSource = "chat-input" | "user-message";

export interface AttachmentPreviewState {
  attachment: MessageAttachment;
  source: AttachmentPreviewSource;
}

const store = createSingletonStore<AttachmentPreviewState | null>(null);

registerPanelCapture(() => {
  const state = store.get();
  if (state) {
    const captured = state;
    return {
      restore: () => store.set(captured),
    };
  }
  return null;
});

export function getAttachmentPreviewState(): AttachmentPreviewState | null {
  return store.get();
}

export function openAttachmentPreview(
  attachment: MessageAttachment,
  source: AttachmentPreviewSource,
): void {
  pushCurrentPanelToHistory();
  store.set({ attachment, source });
}

export function closeAttachmentPreview(): void {
  store.set(null);
}

export function subscribeAttachmentPreview(listener: () => void): () => void {
  return store.subscribe(listener);
}
