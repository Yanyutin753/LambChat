import { createSingletonStore } from "./createSingletonStore";
import { closeCurrentToolPanel } from "./ToolResultPanel";

export interface BlockPreviewData {
  type: "image" | "file" | "text";
  src?: string;
  text?: string;
  url?: string;
  fileName?: string;
}

const store = createSingletonStore<BlockPreviewData | null>(null);

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

export function getBlockPreview(): BlockPreviewData | null {
  return store.get();
}

export function subscribeBlockPreview(listener: () => void): () => void {
  return store.subscribe(listener);
}

export function openBlockPreview(data: BlockPreviewData): void {
  closeCurrentToolPanel();
  if (areBlockPreviewsEqual(store.get(), data)) {
    return;
  }
  store.set(data);
}

export function closeBlockPreview(): void {
  store.set(null);
}
