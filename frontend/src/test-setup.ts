// Conditionally load jest-dom matchers only in jsdom environment.
// Pure-function and source-string tests run under the default "node" environment.
if (typeof document !== "undefined") {
  await import("@testing-library/jest-dom/vitest");

  // Lexical and CodeMirror measure range geometry after focused updates.
  if (typeof Range.prototype.getBoundingClientRect !== "function") {
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  }
  if (typeof Range.prototype.getClientRects !== "function") {
    Range.prototype.getClientRects = () =>
      Object.assign([], { item: () => null });
  }
}
