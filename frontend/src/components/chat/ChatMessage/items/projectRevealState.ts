export const EMPTY_BINARY_FILES: Record<string, string> = {};

export function normalizeProjectRevealBinaryFiles(
  files?: Record<string, string> | null,
): Record<string, string> {
  if (!files) {
    return EMPTY_BINARY_FILES;
  }

  return Object.keys(files).length === 0 ? EMPTY_BINARY_FILES : files;
}

export function areStringRecordMapsEqual(
  left: Record<string, string>,
  right: Record<string, string>,
): boolean {
  if (left === right) {
    return true;
  }

  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);

  if (leftKeys.length !== rightKeys.length) {
    return false;
  }

  for (const key of leftKeys) {
    if (left[key] !== right[key]) {
      return false;
    }
  }

  return true;
}

export function shouldReplaceProjectRevealFiles(
  current: Record<string, string> | null,
  next: Record<string, string> | null,
): boolean {
  if (current === next) {
    return false;
  }

  if (!current || !next) {
    return current !== next;
  }

  return !areStringRecordMapsEqual(current, next);
}
