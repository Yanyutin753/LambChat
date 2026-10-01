/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
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
