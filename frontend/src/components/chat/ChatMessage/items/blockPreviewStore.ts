import { createPanelTabsStore } from "./createPanelTabsStore";

export interface BlockPreviewData {
  type: "image" | "file" | "text";
  src?: string;
  text?: string;
  url?: string;
  fileName?: string;
}

export function blockPreviewKey(data: BlockPreviewData): string {
  return `block-preview:${data.type}:${
    data.src ?? data.url ?? data.fileName ?? data.text ?? "unknown"
  }`;
}
const store = createPanelTabsStore<BlockPreviewData>(blockPreviewKey);
export const getBlockPreview = store.get;
export const getBlockPreviewTabs = store.getAll;
export const subscribeBlockPreview = store.subscribe;
export const clearBlockPreviews = store.clear;

function areBlockPreviewsEqual(
  left: BlockPreviewData | null,
  right: BlockPreviewData | null,
): boolean {
  if (left === right) return true;
  if (!left || !right) return false;
  return (
    left.type === right.type &&
    left.src === right.src &&
    left.text === right.text &&
    left.url === right.url &&
    left.fileName === right.fileName
  );
}

export function openBlockPreview(data: BlockPreviewData): void {
  const existing = store
    .getAll()
    .find((tab) => blockPreviewKey(tab) === blockPreviewKey(data));
  store.open(
    existing && areBlockPreviewsEqual(existing, data) ? existing : data,
  );
}
export function closeBlockPreview(key?: string): void {
  store.close(key);
}
