// Conditionally load jest-dom matchers only in jsdom environment.
// Pure-function and source-string tests run under the default "node" environment.
if (typeof document !== "undefined") {
  await import("@testing-library/jest-dom/vitest");
}
