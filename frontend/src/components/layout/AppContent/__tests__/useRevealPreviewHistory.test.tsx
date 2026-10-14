/** @vitest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Message } from "../../../../types";
import { clearRevealPreviewTabs } from "../../../chat/ChatMessage/items/activeRevealPreviewStore";
import { resetRightPanelCoordinator } from "../../../common/rightPanelCoordinator";
import { useRevealPreview } from "../useRevealPreview";

afterEach(() => {
  act(() => {
    clearRevealPreviewTabs();
    resetRightPanelCoordinator();
  });
  vi.restoreAllMocks();
});

test("loading historical artifacts keeps the preview closed and allows manual opening", () => {
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(1440);
  const messages: Message[] = [
    {
      id: "history-message",
      runId: "completed-run",
      role: "assistant",
      content: "",
      timestamp: new Date(0),
      parts: [
        {
          type: "tool",
          name: "reveal_file",
          args: {},
          success: true,
          result: {
            key: "report.md",
            url: "/api/upload/file/report.md",
            name: "report.md",
            _meta: { path: "/workspace/report.md" },
          },
        },
      ],
    },
  ];
  const { result, rerender } = renderHook(
    ({ history }: { history: Message[] }) =>
      useRevealPreview(history, { current: null }, vi.fn(), true, "session-1", undefined, null, "completed-run"),
    { initialProps: { history: [] as Message[] } },
  );

  rerender({ history: messages });
  expect(result.current.activePreview).toBeNull();

  const preview = {
    kind: "file" as const,
    previewKey: "report.md",
    filePath: "/workspace/report.md",
  };
  act(() => {
    result.current.handleOpenPreview(preview);
  });
  expect(result.current.activePreview).toEqual(preview);
});

test("a run observed active can open its completed artifact without streaming frames", () => {
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(1440);
  const messages: Message[] = [{
    id: "live-message", runId: "live-run", role: "assistant", content: "",
    timestamp: new Date(0),
    parts: [{ type: "tool", name: "reveal_file", args: {}, success: true,
      result: { key: "live.md", url: "/api/upload/file/live.md", name: "live.md",
        _meta: { path: "/workspace/live.md" } } }],
  }];
  const { result, rerender } = renderHook(
    ({ history, active }: { history: Message[]; active: boolean }) =>
      useRevealPreview(history, { current: null }, vi.fn(), true, "session-1", undefined, null, "live-run", active),
    { initialProps: { history: [] as Message[], active: true } },
  );
  rerender({ history: messages, active: false });
  expect(result.current.activePreview?.previewKey).toBe("live.md");
});
