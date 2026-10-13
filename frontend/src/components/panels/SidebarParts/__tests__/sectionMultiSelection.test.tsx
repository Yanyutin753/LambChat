/** @vitest-environment jsdom */
import { createRef, useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { SessionListContent } from "../SessionListContent";
import { sessionApi, type BackendSession } from "../../../../services/api";
import type { Project } from "../../../../types";
import i18n from "../../../../i18n";

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => false }),
}));

const noop = () => {};
const project: Project = {
  id: "project",
  user_id: "user",
  name: "Research",
  type: "custom",
  sort_order: 0,
  created_at: "2026-10-03",
  updated_at: "2026-10-03",
};
const pinned: BackendSession = {
  id: "pinned",
  name: "Pinned chat",
  agent_id: "agent",
  is_active: false,
  created_at: "2026-10-03",
  updated_at: "2026-10-03",
  metadata: { is_pinned: true },
};
const projectChat: BackendSession = {
  ...pinned,
  id: "project-chat",
  name: "Project chat",
  metadata: { project_id: "project" },
};

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.spyOn(sessionApi, "list").mockResolvedValue({
    sessions: [projectChat],
    has_more: false,
    total: 1,
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Sidebar({
  onDelete,
  recent = false,
}: {
  onDelete: (ids: string[]) => void;
  recent?: boolean;
}) {
  const [mode, setMode] = useState(false);
  const [selected, setSelected] = useState(new Set<string>());
  return (
    <MemoryRouter>
      <SessionListContent
        user={null}
        imgError={false}
        onImgError={noop}
        onCollapse={noop}
        compactChrome
        onNewSession={noop}
        onOpenSearch={noop}
        onShowProfile={noop}
        hasMoreMenuItems={false}
        onToggleMoreMenu={noop}
        expandedMoreMenuBtnRef={createRef()}
        scrollEl={null}
        onSetScrollEl={noop}
        uncategorizedSessions={
          recent
            ? [{ ...pinned, id: "recent", name: "Recent chat", metadata: {} }]
            : []
        }
        isUncategorizedLoading={false}
        hasMoreUncategorized={false}
        isLoadingMoreUncategorized={false}
        loadMoreRef={noop}
        onSoftRefreshUncategorized={noop}
        onUpdateUncategorizedSession={noop}
        pinnedSessions={[pinned]}
        isPinnedLoading={false}
        hasMorePinned={false}
        isLoadingMorePinned={false}
        pinnedLoadMoreRef={noop}
        onUpdatePinnedSession={noop}
        isPinnedCollapsed={false}
        onTogglePinnedCollapsed={noop}
        projects={[project]}
        favoritesProject={undefined}
        currentSessionId={null}
        unreadBySession={new Map()}
        sessionActions={{
          onDeleteSession: noop,
          onMoveSession: noop,
          onToggleFavorite: noop,
          onTogglePin: noop,
          onPinSession: noop,
          onShareSession: noop,
          onRequestBatchMoveSessions: noop,
          onRequestBatchDeleteSessions: onDelete,
          onSelectSession: noop,
          onDragStartTouch: noop,
          draggingSessionId: null,
          touchDropTarget: null,
        }}
        projectActions={{
          onRenameProject: noop,
          onDeleteProject: noop,
          onUpdateIcon: noop,
          onOpenNewProjectModal: noop,
          onNewSessionInProject: noop,
          onSetProjectRef: noop,
        }}
        isProjectsCollapsed={false}
        onToggleProjectsCollapsed={noop}
        isNavCollapsed={false}
        onToggleNavCollapsed={noop}
        isChatsCollapsed={false}
        onToggleChatsCollapsed={noop}
        autoExpandProjectId={null}
        onConsumeAutoExpandProjectId={noop}
        onMarkAllRead={noop}
        markingReadId={null}
        isSelectionMode={mode}
        selectedSessionIds={selected}
        onSetSelectionMode={setMode}
        onSetSelectedSessionIds={setSelected}
        onClearSelection={() => {
          setMode(false);
          setSelected(new Set());
        }}
      />
    </MemoryRouter>
  );
}

test.each(["Pinned", "Projects"])(
  "%s starts multi-selection without recent chats",
  async (section) => {
    const onDelete = vi.fn();
    render(<Sidebar onDelete={onDelete} />);
    const header = screen.getByRole("button", { name: section }).parentElement!;
    fireEvent.click(within(header).getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Pinned chat" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Research", exact: true }),
    );
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Project chat" }),
    );
    expect(
      screen.getByRole("checkbox", { name: "Pinned chat" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: "Project chat" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Delete", exact: true }),
    );
    expect(onDelete).toHaveBeenCalledWith(["pinned", "project-chat"]);
    fireEvent.click(
      screen.getByRole("button", { name: "Cancel", exact: true }),
    );
    expect(
      screen.getByRole("button", { name: "Pinned chat" }),
    ).not.toHaveAttribute("aria-checked");
  },
);

test("selection keeps section context and one global count and cancel control", () => {
  render(<Sidebar onDelete={vi.fn()} recent />);
  fireEvent.click(
    screen.getAllByRole("button", { name: "Select", exact: true })[0],
  );
  expect(
    screen.getByRole("button", { name: "Recent chats", exact: true }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "Pinned chat" }));
  expect(screen.getAllByText("1 selected")).toHaveLength(1);
  expect(
    screen.getAllByRole("button", { name: "Cancel", exact: true }),
  ).toHaveLength(1);
  fireEvent.click(
    screen.getByRole("button", {
      name: "Recent chats: Select all",
      exact: true,
    }),
  );
  expect(screen.getByRole("checkbox", { name: "Recent chat" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  expect(screen.getByRole("checkbox", { name: "Pinned chat" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
});
