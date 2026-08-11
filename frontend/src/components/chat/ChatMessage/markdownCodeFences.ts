const FENCE_MARKER_PATTERN = /`{3,}/g;

export function normalizeMarkdownCodeFences(markdown: string): string {
  let result = "";
  let lastIndex = 0;
  let inFence = false;

  FENCE_MARKER_PATTERN.lastIndex = 0;

  for (const match of markdown.matchAll(FENCE_MARKER_PATTERN)) {
    const marker = match[0];
    const markerStart = match.index;
    const markerEnd = markerStart + marker.length;
    const lineStart = markdown.lastIndexOf("\n", markerStart - 1) + 1;
    const nextLineBreak = markdown.indexOf("\n", markerEnd);
    const lineEnd = nextLineBreak === -1 ? markdown.length : nextLineBreak;
    const beforeMarkerOnLine = markdown.slice(lineStart, markerStart);
    const afterMarkerOnLine = markdown.slice(markerEnd, lineEnd);

    if (!inFence) {
      const hasCodeLineAfterOpeningMarker = nextLineBreak !== -1;
      const looksLikeInlineCode =
        beforeMarkerOnLine.includes("`") || afterMarkerOnLine.includes("`");

      if (!hasCodeLineAfterOpeningMarker || looksLikeInlineCode) {
        continue;
      }

      result += markdown.slice(lastIndex, markerStart);
      if (beforeMarkerOnLine.length > 0 && !result.endsWith("\n")) {
        result += "\n";
      }
      result += marker + afterMarkerOnLine;
      lastIndex = lineEnd;
      inFence = true;
      continue;
    }

    if (afterMarkerOnLine.trim().length > 0) {
      continue;
    }

    result += markdown.slice(lastIndex, markerStart);
    if (beforeMarkerOnLine.length > 0 && !result.endsWith("\n")) {
      result += "\n";
    }
    result += marker;
    lastIndex = markerEnd;
    inFence = false;
  }

  return result + markdown.slice(lastIndex);
}
