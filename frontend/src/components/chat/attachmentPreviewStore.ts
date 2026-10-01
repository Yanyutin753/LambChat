import type { MessageAttachment } from "../../types";
import { createPanelTabsStore } from "./ChatMessage/items/createPanelTabsStore";

export type AttachmentPreviewSource = "chat-input" | "user-message";

export interface AttachmentPreviewState {
  attachment: MessageAttachment;
  source: AttachmentPreviewSource;
}

export function attachmentPreviewKey(state: AttachmentPreviewState): string {
  return `attachment-preview:${state.attachment.key}`;
}
const store =
  createPanelTabsStore<AttachmentPreviewState>(attachmentPreviewKey);
export const getAttachmentPreviewState = store.get;
export const getAttachmentPreviewTabs = store.getAll;
export const subscribeAttachmentPreview = store.subscribe;
export const clearAttachmentPreviews = store.clear;

export function openAttachmentPreview(
  attachment: MessageAttachment,
  source: AttachmentPreviewSource,
): void {
  store.open({ attachment, source });
}
export function closeAttachmentPreview(key?: string): void {
  store.close(key);
}
