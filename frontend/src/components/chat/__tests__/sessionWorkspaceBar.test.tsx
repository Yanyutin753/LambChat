/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { SessionWorkspaceBar } from "../SessionWorkspaceBar";

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  current: "m1" as string | null,
}));
vi.mock("../../../hooks/useSandboxStatus", () => ({
  useSandboxStatus: () => ({
    currentMachineId: mocks.current,
    defaultMachineId: "m1",
    machines: [{ machine_id: "m1", online: true }],
  }),
}));
vi.mock("../../../services/tauri/sandboxShell", () => ({
  invokeInShell: mocks.invoke,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("react-hot-toast", () => ({ toast: { error: vi.fn() } }));

afterEach(cleanup);
beforeEach(() => {
  mocks.invoke.mockReset();
  mocks.current = "m1";
});

test("native selection pins the machine and saves the directory in session options", async () => {
  const picked = {
    id: `local-${"a".repeat(32)}`,
    machineId: "m1",
    path: "/home/project",
  };
  mocks.invoke.mockResolvedValue(picked);
  const onChange = vi.fn();
  render(
    <SessionWorkspaceBar
      values={{ sandbox: "local" }}
      onChange={onChange}
      disabled={false}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "sessionWorkspace.choose" }),
  );
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      "sandbox_workspace",
      JSON.stringify(picked),
    ),
  );
  expect(onChange).toHaveBeenCalledWith("sandbox_machine_id", "m1");
});

test("cancelling preserves session options", async () => {
  mocks.invoke.mockResolvedValue(null);
  const onChange = vi.fn();
  render(
    <SessionWorkspaceBar
      values={{ sandbox: "local" }}
      onChange={onChange}
      disabled={false}
    />,
  );
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(screen.getByRole("button")).not.toBeDisabled());
  expect(onChange).not.toHaveBeenCalled();
});

test("browser clients do not show a native directory entry", () => {
  mocks.current = null;
  render(
    <SessionWorkspaceBar
      values={{ sandbox: "local" }}
      onChange={vi.fn()}
      disabled={false}
    />,
  );
  expect(screen.queryByRole("button")).toBeNull();
});

test("running sessions cannot change their execution directory", () => {
  render(
    <SessionWorkspaceBar
      values={{ sandbox: "local" }}
      onChange={vi.fn()}
      disabled
    />,
  );
  expect(screen.getByRole("button")).toBeDisabled();
});
