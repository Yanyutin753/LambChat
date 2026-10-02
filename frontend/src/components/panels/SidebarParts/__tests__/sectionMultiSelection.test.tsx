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

function Sidebar({ onDelete }: { onDelete: (ids: string[]) => void }) {
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
        uncategorizedSessions={[]}
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
    fireEvent.click(screen.getByRole("button", { name: "Pinned chat" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Research", exact: true }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Project chat" }),
    );
    expect(screen.getByRole("button", { name: "Pinned chat" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByRole("button", { name: "Project chat" }),
    ).toHaveAttribute("aria-pressed", "true");
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
    ).not.toHaveAttribute("aria-pressed");
  },
);
