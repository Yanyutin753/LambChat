/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import type { BookmarkItem } from "../../../services/api/bookmark";
import { BookmarksPanel } from "../BookmarksPanel";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const { toggleMock } = vi.hoisted(() => ({ toggleMock: vi.fn() }));
vi.mock("../../../stores/bookmarkStore", () => ({
  ensureBookmarksLoaded: vi.fn(),
  toggleMessageBookmark: toggleMock,
}));

const state: { status: "ready"; items: BookmarkItem[] } = {
  status: "ready",
  items: [],
};
vi.mock("../../../hooks/useBookmarks", () => ({
  useBookmarks: () => state,
}));

function makeBookmark(overrides: Partial<BookmarkItem> = {}): BookmarkItem {
  return {
    id: "bm-1",
    user_id: "user-1",
    session_id: "session-1",
    message_id: "run-1",
    run_id: "run-1",
    label: "季度规划大纲",
    created_at: "2026-08-01T12:00:00Z",
    session_name: "产品讨论",
    session_is_active: true,
    ...overrides,
  };
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
  navigateMock.mockClear();
  toggleMock.mockClear();
});

test("renders bookmarks with label and session name", () => {
  state.items = [makeBookmark()];

  render(<BookmarksPanel />);

  expect(screen.getByText("季度规划大纲")).toBeInTheDocument();
  expect(screen.getByText("产品讨论")).toBeInTheDocument();
});

test("clicking a bookmark navigates to the session with run deep link", () => {
  state.items = [makeBookmark()];

  render(<BookmarksPanel />);
  fireEvent.click(screen.getByText("季度规划大纲"));

  expect(navigateMock).toHaveBeenCalledWith("/chat/session-1?run_id=run-1");
});

test("user-message bookmarks strip the :user suffix for the deep link", () => {
  state.items = [makeBookmark({ message_id: "run-42:user", run_id: null })];

  render(<BookmarksPanel />);
  fireEvent.click(screen.getByText("季度规划大纲"));

  expect(navigateMock).toHaveBeenCalledWith("/chat/session-1?run_id=run-42");
});

test("remove button toggles the bookmark off without navigating", () => {
  state.items = [makeBookmark()];
  toggleMock.mockResolvedValue({ bookmarked: false });

  render(<BookmarksPanel />);
  fireEvent.click(screen.getByRole("button", { name: "Remove bookmark" }));

  expect(toggleMock).toHaveBeenCalledWith({
    sessionId: "session-1",
    messageId: "run-1",
  });
  expect(navigateMock).not.toHaveBeenCalled();
});

test("shows the empty hint when there are no bookmarks", () => {
  state.items = [];

  render(<BookmarksPanel />);

  expect(screen.getByText("No bookmarks yet")).toBeInTheDocument();
  expect(
    screen.getByText(/bookmark icon to save outlines/i),
  ).toBeInTheDocument();
});
