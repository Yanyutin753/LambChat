/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ProjectItem } from "../ProjectItem";
import { sessionApi } from "../../../services/api";
import type { Project } from "../../../types";
import i18n from "../../../i18n";

const project: Project = {
  id: "project-1",
  user_id: "user-1",
  name: "LambChat",
  type: "custom",
  sort_order: 0,
  created_at: "2026-09-30",
  updated_at: "2026-09-30",
};

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.spyOn(sessionApi, "list").mockResolvedValue({
    sessions: [],
    has_more: false,
    total: 0,
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function renderProject(value = project) {
  const onNewSessionInProject = vi.fn();
  render(
    <ProjectItem
      project={value}
      currentSessionId={null}
      allProjects={[value]}
      onSelectSession={vi.fn()}
      onDeleteSession={vi.fn()}
      onMoveSession={vi.fn()}
      onRenameProject={vi.fn()}
      onDeleteProject={vi.fn()}
      onNewSessionInProject={onNewSessionInProject}
    />,
  );
  return onNewSessionInProject;
}

test("a collapsed project offers one-click new chat without opening its menu or toggling the list", () => {
  const onNew = renderProject();
  fireEvent.click(screen.getByRole("button", { name: "New chat in LambChat" }));
  expect(onNew).toHaveBeenCalledExactlyOnceWith("project-1");
  expect(screen.getByRole("button", { name: "LambChat" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(sessionApi.list).not.toHaveBeenCalled();
});

test("an expanded empty project has a direct first-chat action", async () => {
  const onNew = renderProject();
  fireEvent.click(screen.getByRole("button", { name: "LambChat" }));
  const start = await screen.findByRole("button", {
    name: "Start your first chat",
  });
  fireEvent.click(start);
  expect(onNew).toHaveBeenCalledExactlyOnceWith("project-1");
  expect(screen.getByRole("button", { name: "LambChat" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await waitFor(() => expect(sessionApi.list).toHaveBeenCalled());
});

test("favorites offer no project-scoped creation action", () => {
  renderProject({ ...project, type: "favorites" });
  expect(
    screen.queryByRole("button", { name: /New chat in/ }),
  ).not.toBeInTheDocument();
});

test("touch reveals only the current project's actions and renews their timeout", () => {
  vi.useFakeTimers();
  renderProject();
  renderProject({ ...project, id: "project-2", name: "Other project" });
  const row = screen
    .getByRole("button", { name: "LambChat" })
    .closest(".sidebar-action-row")!;
  const current = row.querySelector(".sidebar-action-reveal")!;
  const other = screen
    .getByRole("button", { name: "Other project" })
    .closest(".sidebar-action-row")!
    .querySelector(".sidebar-action-reveal")!;
  expect(current).not.toHaveAttribute("data-revealed", "true");
  fireEvent.touchStart(row);
  expect(current).toHaveAttribute("data-revealed", "true");
  expect(other).not.toHaveAttribute("data-revealed", "true");
  act(() => vi.advanceTimersByTime(2000));
  fireEvent.touchStart(row);
  act(() => vi.advanceTimersByTime(2999));
  expect(current).toHaveAttribute("data-revealed", "true");
  act(() => vi.advanceTimersByTime(1));
  expect(current).not.toHaveAttribute("data-revealed", "true");
});

test("an open project menu keeps actions revealed after the touch timeout", () => {
  vi.useFakeTimers();
  renderProject();
  const row = screen
    .getByRole("button", { name: "LambChat" })
    .closest(".sidebar-action-row")!;
  const actions = row.querySelector(".sidebar-action-reveal")!;
  fireEvent.touchStart(row);
  fireEvent.click(screen.getByRole("button", { name: "More options" }));
  act(() => vi.advanceTimersByTime(3000));
  expect(actions).toHaveAttribute("data-revealed", "true");
  expect(screen.getByRole("button", { name: "Rename" })).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(actions).not.toHaveAttribute("data-revealed", "true");
});
