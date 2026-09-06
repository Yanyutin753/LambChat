/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import type { BookmarkItem } from "../../../services/api/bookmark";
import { BookmarkButton } from "../BookmarkButton";

const state: { status: "ready"; items: BookmarkItem[] } = {
  status: "ready",
  items: [],
};
vi.mock("../../../../hooks/useBookmarks", () => ({
  useBookmarks: () => state,
}));

const { toggleMock } = vi.hoisted(() => ({ toggleMock: vi.fn() }));
vi.mock("../../../../stores/bookmarkStore", () => ({
  toggleMessageBookmark: toggleMock,
}));

function makeBookmark(): BookmarkItem {
  return {
    id: "bm-1",
    user_id: "user-1",
    session_id: "session-1",
    message_id: "message-1",
    run_id: "run-1",
    label: null,
    created_at: "2026-08-01T12:00:00Z",
    session_name: null,
    session_is_active: true,
  };
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
  toggleMock.mockClear();
  toggleMock.mockResolvedValue({ bookmarked: true });
});

test("renders unbookmarked state by default", () => {
  state.items = [];

  render(
    <BookmarkButton
      sessionId="session-1"
      messageId="message-1"
      runId="run-1"
    />,
  );

  const button = screen.getByRole("button", { name: "Add bookmark" });
  expect(button.getAttribute("aria-pressed")).toBe("false");
});

test("renders bookmarked state when the message is saved", () => {
  state.items = [makeBookmark()];

  render(
    <BookmarkButton
      sessionId="session-1"
      messageId="message-1"
      runId="run-1"
    />,
  );

  const button = screen.getByRole("button", { name: "Remove bookmark" });
  expect(button.getAttribute("aria-pressed")).toBe("true");
});

test("clicking toggles the bookmark with label and run id", () => {
  state.items = [];

  render(
    <BookmarkButton
      sessionId="session-1"
      messageId="message-1"
      runId="run-1"
      label="季度规划大纲"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Add bookmark" }));

  expect(toggleMock).toHaveBeenCalledWith({
    sessionId: "session-1",
    messageId: "message-1",
    runId: "run-1",
    label: "季度规划大纲",
  });
});
