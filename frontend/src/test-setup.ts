// Conditionally load jest-dom matchers only in jsdom environment.
// Pure-function and source-string tests run under the default "node" environment.
if (typeof document !== "undefined") {
  await import("@testing-library/jest-dom/vitest");

  // jsdom does not implement range geometry, but Lexical measures the active
  // caret after focused editor updates to keep it in view.
  if (typeof Range.prototype.getBoundingClientRect !== "function") {
    Range.prototype.getBoundingClientRect = () => new DOMRect();
  }
}
