/** Stable leading context for panel titles, including streamed prose. */
export function buildPanelSummary(content: string): string | undefined {
  const text = content.replace(/\s+/g, " ").trim();
  if (!text) return undefined;
  return text.length > 120 ? `${text.slice(0, 119)}…` : text;
}
