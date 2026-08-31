/** @vitest-environment jsdom */

import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import type { BookmarkItem } from "../../../services/api/bookmark";
import {
  closePersistentToolPanel,
  isPersistentToolPanelOpen,
} from "../ChatMessage/items/persistentToolPanelState";
import {
  SessionBookmarksButton,
  SessionBookmarksPanelBody,
} from "../SessionBookmarksButton";

const state: { status: "ready"; items: BookmarkItem[] } = {
  status: "ready",
  items: [],
};
vi.mock("../../../hooks/useBookmarks", () => ({
  useBookmarks: () => state,
}));

const { removeMock } = vi.hoisted(() => ({ removeMock: vi.fn() }));
vi.mock("../../../stores/bookmarkStore", () => ({
  toggleMessageBookmark: removeMock,
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
  closePersistentToolPanel();
  cleanup();
  removeMock.mockReset();
  removeMock.mockResolvedValue({ bookmarked: false });
  state.items = [];
});

test("renders nothing when the session has no bookmarks", () => {
  state.items = [makeBookmark({ session_id: "session-2" })];

  const { container } = render(
    <SessionBookmarksButton sessionId="session-1" />,
  );

  expect(container.querySelector("button")).toBeNull();
});

test("renders a floating button with the session bookmark count", () => {
  state.items = [
    makeBookmark(),
    makeBookmark({ id: "bm-2", message_id: "run-2", label: "周会纪要" }),
    makeBookmark({ session_id: "session-2", id: "bm-3" }),
  ];

  render(<SessionBookmarksButton sessionId="session-1" />);

  const button = screen.getByRole("button", { name: /bookmarks/i });
  expect(button.textContent).toContain("2");
});

test("clicking the button opens the persistent tool panel with entries", () => {
  state.items = [makeBookmark()];

  render(<SessionBookmarksButton sessionId="session-1" />);
  fireEvent.click(screen.getByRole("button", { name: /bookmarks/i }));

  expect(isPersistentToolPanelOpen()).toBe(true);
});

test("jumping from an entry closes the panel and navigates to the message", () => {
  state.items = [makeBookmark()];
  const onNavigateToMessage = vi.fn();

  render(
    <SessionBookmarksPanelBody
      bookmarks={state.items}
      onJump={(messageId) => {
        closePersistentToolPanel();
        onNavigateToMessage(messageId);
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /jump/i }));

  expect(onNavigateToMessage).toHaveBeenCalledWith("run-1");
  expect(isPersistentToolPanelOpen()).toBe(false);
});

test("panel body lists bookmark entries for the session", () => {
  state.items = [makeBookmark()];

  render(<SessionBookmarksPanelBody bookmarks={state.items} onJump={() => {}} />);

  expect(screen.getByText("季度规划大纲")).toBeInTheDocument();
});

test("removing an entry keeps the panel open for the remaining ones", () => {
  state.items = [makeBookmark()];

  render(
    <SessionBookmarksPanelBody
      bookmarks={state.items}
      onJump={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /remove bookmark/i }));

  expect(removeMock).toHaveBeenCalledWith({
    sessionId: "session-1",
    messageId: "run-1",
  });
});
