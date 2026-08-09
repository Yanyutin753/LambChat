import type {
  ComposerSnapshot,
  DecodedComposerHistoryEntry,
} from "./composerTypes";

function isComposerSnapshot(value: unknown): value is ComposerSnapshot {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ComposerSnapshot>;
  return (
    candidate.version === 1 &&
    !!candidate.editorState &&
    typeof candidate.editorState === "object"
  );
}

export function decodeComposerHistoryEntry(
  value: string,
): DecodedComposerHistoryEntry {
  try {
    const parsed: unknown = JSON.parse(value);
    if (isComposerSnapshot(parsed)) return parsed;
  } catch {
    // Legacy prompt text is intentionally not required to be valid JSON.
  }
  return { version: 0, plainText: value };
}
