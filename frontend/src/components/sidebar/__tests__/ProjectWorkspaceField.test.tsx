/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ProjectWorkspaceField } from "../ProjectWorkspaceField";
const invoke = vi.hoisted(() => vi.fn());
vi.mock("../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: () => true,
  invokeInShell: invoke,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

test("native selection binds the machine receipt and clear removes only the binding", async () => {
  const selection = {
    id: "local-" + "a".repeat(32),
    machineId: "mac",
    path: "/Users/me/repo",
  };
  invoke.mockResolvedValue(selection);
  const onChange = vi.fn();
  const { rerender } = render(
    <ProjectWorkspaceField value={null} onChange={onChange} />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "projectWorkspace.choose" }),
  );
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(selection));
  expect(invoke).toHaveBeenCalledWith(
    "sandbox_pick_workspace",
    expect.any(Object),
  );
  rerender(<ProjectWorkspaceField value={selection} onChange={onChange} />);
  expect(screen.getByText(selection.path)).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "projectWorkspace.clear" }),
  );
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(null));
});

afterEach(cleanup);

test("workspace details stay hidden until requested and dismiss without toggling the project", () => {
  const onToggle = vi.fn();
  const selection = {
    id: "local-test",
    machineId: "mac",
    path: "/Users/me/very-long-project-directory",
  };
  render(
    <div onClick={onToggle}>
      <ProjectWorkspaceField value={selection} onChange={vi.fn()} />
    </div>,
  );
  expect(
    screen.queryByText("projectWorkspace.inherits"),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "projectWorkspace.details" }),
  );
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText(selection.path)).toBeInTheDocument();
  expect(
    within(dialog).getByText("projectWorkspace.inherits"),
  ).toBeInTheDocument();
  expect(onToggle).not.toHaveBeenCalled();
  fireEvent.click(
    within(dialog).getByRole("button", { name: "common.dismiss" }),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(onToggle).not.toHaveBeenCalled();
});
