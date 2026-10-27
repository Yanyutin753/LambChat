/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { SessionWorkspaceBar } from "../SessionWorkspaceBar";
import { createRef } from "react";
import type { SessionWorkspaceBarHandle } from "../SessionWorkspaceBar";
import { API_BASE } from "../../../services/api/config";

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "user" } }),
}));

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  locations: vi.fn(),
  current: "m1" as string | null,
  online: true,
  defaultId: "m1" as string | null,
  shell: false,
}));
vi.mock("../../../services/api/session", () => ({
  sessionApi: { getWorkspaceLocations: mocks.locations },
}));
vi.mock("../../../hooks/useSandboxStatus", () => ({
  useSandboxStatus: () => ({
    currentMachineId: mocks.current,
    defaultMachineId: mocks.defaultId,
    machines: [{ machine_id: "m1", online: mocks.online }],
  }),
}));
vi.mock("../../../services/tauri/sandboxShell", () => ({
  invokeInShell: mocks.invoke,
  isShellAvailable: () => mocks.shell,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("react-hot-toast", () => ({ toast: { error: vi.fn() } }));

afterEach(cleanup);
beforeEach(() => {
  localStorage.clear();
  mocks.invoke.mockReset();
  mocks.locations.mockReset().mockResolvedValue({ locations: [] });
  mocks.current = "m1";
  mocks.online = true;
  mocks.defaultId = "m1";
  mocks.shell = false;
});

test("native identity must resolve before local submission can choose its workspace", async () => {
  mocks.shell = true;
  mocks.current = null;
  const ref = createRef<SessionWorkspaceBarHandle>();
  const props = {
    ref,
    values: { sandbox: "local" },
    onChange: vi.fn(),
    disabled: false,
  };
  const { rerender } = render(<SessionWorkspaceBar {...props} />);
  expect(ref.current?.prepareSubmit()).toBe(false);
  expect(mocks.invoke).not.toHaveBeenCalled();
  expect(screen.queryByText("sessionWorkspace.independent")).toBeNull();
  mocks.current = "m1";
  rerender(<SessionWorkspaceBar {...props} />);
  await act(async () => expect(ref.current?.prepareSubmit()).toBe(false));
  expect(mocks.invoke).toHaveBeenCalledTimes(1);
});

test("local submission selects a real directory before allowing execution", async () => {
  const ref = createRef<SessionWorkspaceBarHandle>();
  const picked = {
    id: `local-${"a".repeat(32)}`,
    machineId: "m1",
    path: "/home/project",
  };
  mocks.invoke.mockResolvedValue(picked);
  const onChange = vi.fn();
  const props = { ref, onChange, disabled: false };
  const { rerender } = render(
    <SessionWorkspaceBar {...props} values={{ sandbox: "local" }} />,
  );
  expect(screen.queryByText("sessionWorkspace.independent")).toBeNull();
  act(() => expect(ref.current?.prepareSubmit()).toBe(false));
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      "sandbox_workspace",
      JSON.stringify(picked),
    ),
  );
  rerender(
    <SessionWorkspaceBar
      {...props}
      values={{
        sandbox: "local",
        sandbox_machine_id: "m1",
        sandbox_workspace: JSON.stringify(picked),
      }}
    />,
  );
  expect(ref.current?.prepareSubmit()).toBe(true);
  expect(screen.getByText("project")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "sessionWorkspace.reset" }),
  ).toBeNull();
});

test.each(["cloud", "local"])(
  "%s execution outside this client keeps its existing workspace behavior",
  (sandbox) => {
    mocks.current = null;
    const ref = createRef<SessionWorkspaceBarHandle>();
    render(
      <SessionWorkspaceBar
        ref={ref}
        values={{ sandbox }}
        onChange={vi.fn()}
        disabled={false}
      />,
    );
    expect(ref.current?.prepareSubmit()).toBe(true);
    expect(mocks.invoke).not.toHaveBeenCalled();
  },
);

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
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(
    localStorage.getItem(
      `localWorkspace:${JSON.stringify([API_BASE, "user", "m1"])}`,
    ),
  ).toBe(JSON.stringify(picked));
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
  expect(screen.getByText("sessionWorkspace.independent")).toBeVisible();
});

test("cloud conversations explain their independent directory without a native picker", () => {
  render(
    <SessionWorkspaceBar values={{ sandbox: "cloud" }} disabled={false} />,
  );
  expect(screen.getByText("sessionWorkspace.independent")).toBeVisible();
  expect(screen.queryByRole("button")).toBeNull();
});

test("invalid bindings are shown as unavailable instead of a different folder", () => {
  render(
    <SessionWorkspaceBar
      values={{ sandbox: "local", sandbox_workspace: "not-json" }}
      onChange={vi.fn()}
      disabled={false}
    />,
  );
  expect(
    screen.getByText("backendErrors.sandboxWorkspaceInvalid"),
  ).toBeVisible();
  expect(screen.queryByText("sessionWorkspace.independent")).toBeNull();
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

test("a picker opened before execution cannot change the directory after execution starts", async () => {
  let finish!: (value: object) => void;
  mocks.invoke.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const values = { sandbox: "local" };
  const onChange = vi.fn();
  const { rerender } = render(
    <SessionWorkspaceBar
      values={values}
      onChange={onChange}
      disabled={false}
    />,
  );
  fireEvent.click(screen.getByRole("button"));
  rerender(
    <SessionWorkspaceBar values={values} onChange={onChange} disabled />,
  );
  finish({ id: `local-${"a".repeat(32)}`, machineId: "m1", path: "/repo" });
  await waitFor(() =>
    expect(screen.queryByText("sessionWorkspace.loading")).toBeNull(),
  );
  expect(onChange).not.toHaveBeenCalled();
});

test("web sessions show the inherited directory without exposing its full path or native controls", () => {
  mocks.current = null;
  render(
    <SessionWorkspaceBar
      values={{
        sandbox: "local",
        sandbox_machine_id: "m1",
        sandbox_workspace: JSON.stringify({
          id: `local-${"a".repeat(32)}`,
          machineId: "m1",
          path: "/Users/private/project",
        }),
      }}
      onChange={vi.fn()}
      disabled={false}
    />,
  );
  expect(screen.getByText("project")).toBeVisible();
  expect(screen.queryByText("/Users/private/project")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
});

test("reconnecting keeps the directory entry visible and disables it until online", () => {
  const props = {
    values: { sandbox: "local", sandbox_machine_id: "m1" },
    onChange: vi.fn(),
    disabled: false,
  };
  const { rerender } = render(<SessionWorkspaceBar {...props} />);
  expect(
    screen.getByRole("button", { name: "sessionWorkspace.choose" }),
  ).toBeEnabled();
  mocks.online = false;
  rerender(<SessionWorkspaceBar {...props} />);
  expect(
    screen.getByRole("button", { name: "sessionWorkspace.choose" }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "sessionWorkspace.choose" }),
  ).toBeDisabled();
  mocks.online = true;
  rerender(<SessionWorkspaceBar {...props} />);
  expect(
    screen.getByRole("button", { name: "sessionWorkspace.choose" }),
  ).toBeEnabled();
});

test("an implicit sole machine keeps its workspace entry when it disconnects", () => {
  mocks.defaultId = null;
  const props = {
    values: { sandbox: "local" },
    onChange: vi.fn(),
    disabled: false,
  };
  const { rerender } = render(<SessionWorkspaceBar {...props} />);
  expect(
    screen.getByRole("button", { name: "sessionWorkspace.choose" }),
  ).toBeEnabled();
  mocks.online = false;
  rerender(<SessionWorkspaceBar {...props} />);
  expect(
    screen.getByRole("button", { name: "sessionWorkspace.choose" }),
  ).toBeDisabled();
});

test("previous local locations restore the whole binding without reopening the native picker", async () => {
  const previous = {
    id: `local-${"b".repeat(32)}`,
    machineId: "m1",
    path: "/previous",
  };
  mocks.locations.mockResolvedValue({
    locations: [
      {
        id: "old",
        options: {
          sandbox: "local",
          sandbox_machine_id: "m1",
          sandbox_workspace: JSON.stringify(previous),
        },
        saved_at: "2026-10-27",
      },
      {
        id: "other",
        options: {
          sandbox: "local",
          sandbox_machine_id: "m2",
          sandbox_workspace: JSON.stringify({
            ...previous,
            machineId: "m2",
            path: "/other",
          }),
        },
      },
    ],
  });
  const onChange = vi.fn();
  render(
    <SessionWorkspaceBar
      sessionId="s1"
      values={{ sandbox: "local", sandbox_machine_id: "m1" }}
      onChange={onChange}
      disabled={false}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "sessionWorkspace.previous" }),
  );
  fireEvent.click(screen.getByRole("option", { name: "/previous" }));
  expect(onChange).toHaveBeenCalledWith(
    "sandbox_workspace",
    JSON.stringify(previous),
  );
  expect(mocks.invoke).not.toHaveBeenCalled();
  expect(screen.queryByText("/other")).toBeNull();
});

test("history loading failures show retry without changing the current directory", async () => {
  mocks.locations.mockRejectedValueOnce(new Error("offline"));
  const onChange = vi.fn();
  render(
    <SessionWorkspaceBar
      sessionId="s1"
      values={{ sandbox: "local", sandbox_machine_id: "m1" }}
      onChange={onChange}
      disabled={false}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "sessionWorkspace.previous" }),
  );
  await waitFor(() => expect(mocks.locations).toHaveBeenCalledTimes(2));
  expect(onChange).not.toHaveBeenCalled();
});

test("new chats do not request previous locations", () => {
  render(
    <SessionWorkspaceBar
      values={{ sandbox: "local", sandbox_machine_id: "m1" }}
      onChange={vi.fn()}
      disabled={false}
    />,
  );
  expect(mocks.locations).not.toHaveBeenCalled();
});

test("a closed environment panel keeps the workspace submission guard mounted", async () => {
  mocks.shell = true;
  mocks.invoke.mockResolvedValue(null);
  const ref = createRef<SessionWorkspaceBarHandle>();
  const { container } = render(
    <SessionWorkspaceBar
      ref={ref}
      host={null}
      values={{ sandbox: "local", sandbox_machine_id: "m1" }}
      onChange={vi.fn()}
      disabled={false}
    />,
  );
  expect(container).toBeEmptyDOMElement();
  await act(async () => expect(ref.current?.prepareSubmit()).toBe(false));
  expect(mocks.invoke).toHaveBeenCalledTimes(1);
});

test.each([true, false])(
  "portaled directory labels show only the last folder (editable: %s)",
  (editable) => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    try {
      render(
        <SessionWorkspaceBar
          host={host}
          values={{
            sandbox: "local",
            sandbox_machine_id: "m1",
            sandbox_workspace: JSON.stringify({
              id: `local-${"a".repeat(32)}`,
              machineId: "m1",
              path: "/private/tmp/lambchat-project-check/",
            }),
          }}
          onChange={editable ? vi.fn() : undefined}
          disabled={false}
        />,
      );
      expect(host.textContent).toBe("lambchat-project-check");
    } finally {
      host.remove();
    }
  },
);
