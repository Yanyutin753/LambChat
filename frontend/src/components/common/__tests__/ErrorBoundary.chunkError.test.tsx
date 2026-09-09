/** @vitest-environment jsdom */

import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";

vi.mock("../../../utils/chunkLoadRecovery", () => ({
  attemptChunkReload: vi.fn(() => true),
  isChunkLoadError: vi.fn((error: unknown) =>
    Boolean(
      error instanceof Error &&
        error.message.includes(
          "Failed to fetch dynamically imported module",
        ),
    ),
  ),
}));

import { ErrorBoundary } from "../ErrorBoundary";
import { attemptChunkReload } from "../../../utils/chunkLoadRecovery";

function Bomb({ error }: { error: Error }): ReactNode {
  throw error;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test("chunk load errors render the friendly updating UI and self-heal", () => {
  // 桌面端更新后旧 chunk 404 不再裸报 Failed to fetch dynamically
  // imported module：走「资源更新中」分支并自动带缓存参数重载一次。
  const consoleError = vi
    .spyOn(console, "error")
    .mockImplementation(() => undefined);

  render(
    <ErrorBoundary>
      <Bomb
        error={new Error(
          "Failed to fetch dynamically imported module: http://tauri.localhost/assets/RichChatComposer-6TNnBJWu.js",
        )}
      />
    </ErrorBoundary>,
  );

  expect(attemptChunkReload).toHaveBeenCalledTimes(1);
  expect(document.body.textContent).not.toContain(
    "Failed to fetch dynamically imported module",
  );

  consoleError.mockRestore();
});

test("non-chunk errors keep the raw message and never auto-reload", () => {
  const consoleError = vi
    .spyOn(console, "error")
    .mockImplementation(() => undefined);

  render(
    <ErrorBoundary>
      <Bomb error={new ReferenceError("x is not defined")} />
    </ErrorBoundary>,
  );

  expect(attemptChunkReload).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain("x is not defined");

  consoleError.mockRestore();
});
