// Streaming preview for the thinking pill label — shows the latest few
// characters of the reasoning so the user can see it updating live.

// Slice a bounded tail window before flattening so per-delta cost stays
// constant regardless of how long the reasoning grows.
const TAIL_WINDOW = 60;

export const STREAMING_PREVIEW_MAX_LEN = 24;

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

export function buildStreamingThinkingPreview(content: string): string {
  if (!content) return "";
  let window = content.slice(-TAIL_WINDOW);
  if (isHighSurrogate(window.charCodeAt(0))) window = window.slice(1);
  const text = window.replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (text.length <= STREAMING_PREVIEW_MAX_LEN) return text;
  let tail = text.slice(-STREAMING_PREVIEW_MAX_LEN);
  if (isHighSurrogate(tail.charCodeAt(0))) tail = tail.slice(1);
  return tail.trimStart();
}
