/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useWorkspaceOptionActions } from "../sessionToggleCallbacks";
import type { AgentInfo } from "../../../../types";
import * as workspaceApi from "../../../../services/api/sessionWorkspace";
import {
  useAgentOptions,
  SANDBOX_ONLINE_CHANGED_EVENT,
} from "../useAgentOptions";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

const onlineStatus = {
  online: true,
  defaultMachineId: "remote-pc",
  currentMachineId: "this-mac",
  machines: ["remote-pc", "this-mac"].map((machine_id) => ({
    machine_id,
    name: machine_id,
    platform: "darwin",
    version: "2.15.2",
    confirm_policy: "all",
    online: true,
  })),
};

test("new local conversations pin the client computer instead of the account default", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result } = renderHook(() =>
    useAgentOptions(agents, "fast", onlineStatus),
  );
  expect(result.current.agentOptionValues).toMatchObject({
    sandbox: "local",
    sandbox_machine_id: "this-mac",
  });
});

test("a client identity arriving after presence pins the untouched local draft", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result, rerender } = renderHook(
    ({ machineId }: { machineId: string | null }) =>
      useAgentOptions(agents, "fast", {
        ...onlineStatus,
        currentMachineId: machineId,
      }),
    { initialProps: { machineId: null } },
  );
  rerender({ machineId: "this-mac" });
  expect(result.current.agentOptionValues.sandbox_machine_id).toBe("this-mac");
});

test.each(["remote-pc", ""])(
  "an explicit machine selection %j survives late client identity",
  (selected) => {
    const agents = [{ id: "fast", options: {} }] as AgentInfo[];
    const { result, rerender } = renderHook(
      ({ machineId }: { machineId: string | null }) =>
        useAgentOptions(agents, "fast", {
          ...onlineStatus,
          currentMachineId: machineId,
        }),
      { initialProps: { machineId: null } },
    );
    act(() =>
      result.current.handleToggleAgentOption("sandbox_machine_id", selected),
    );
    rerender({ machineId: "this-mac" });
    expect(result.current.agentOptionValues.sandbox_machine_id).toBe(selected);
    act(() => result.current.resetAgentOptionDefaults());
    expect(result.current.agentOptionValues.sandbox_machine_id).toBe(
      "this-mac",
    );
  },
);

test.each<Record<string, boolean | string | number>>([
  { sandbox: "local", sandbox_machine_id: "remote-pc" },
  { sandbox: "local" },
  { sandbox: "cloud" },
])("restored options %j survive late client identity", (restored) => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result, rerender } = renderHook(
    ({ machineId }: { machineId: string | null }) =>
      useAgentOptions(agents, "fast", {
        ...onlineStatus,
        currentMachineId: machineId,
      }),
    { initialProps: { machineId: null } },
  );
  act(() => result.current.restoreAgentOptions(restored));
  rerender({ machineId: "this-mac" });
  expect(result.current.agentOptionValues).toEqual(restored);
});

test("cloud preference stays cloud and choosing local then pins the client computer", () => {
  localStorage.setItem("defaultSandboxMode", "cloud");
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result } = renderHook(() =>
    useAgentOptions(agents, "fast", onlineStatus),
  );
  expect(result.current.agentOptionValues).toEqual({ sandbox: "cloud" });
  act(() => result.current.handleToggleAgentOption("sandbox", "local"));
  expect(result.current.agentOptionValues.sandbox_machine_id).toBe("this-mac");
});

test("switching an existing chat to local persists the same machine shown in the composer", () => {
  localStorage.setItem("defaultSandboxMode", "cloud");
  const save = vi
    .spyOn(workspaceApi, "saveSessionWorkspaceOptions")
    .mockResolvedValue(undefined);
  const agents = [{ id: "search", options: {} }] as AgentInfo[];
  const { result } = renderHook(() => {
    const options = useAgentOptions(agents, "search", onlineStatus);
    const actions = useWorkspaceOptionActions(
      "session",
      options.handleToggleAgentOption,
      vi.fn(),
    );
    return { ...options, ...actions };
  });
  act(() => result.current.changeOption("sandbox", "local"));
  expect(save).toHaveBeenCalledWith("session", {
    sandbox: "local",
    sandbox_machine_id: "this-mac",
  });
  expect(result.current.agentOptionValues.sandbox_machine_id).toBe("this-mac");
});

test("without an online client computer the draft keeps server automatic selection", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result } = renderHook(() =>
    useAgentOptions(agents, "fast", {
      ...onlineStatus,
      machines: [{ ...onlineStatus.machines[1], online: false }],
    }),
  );
  expect(result.current.agentOptionValues).toEqual({ sandbox: "local" });
});

test("the selected client computer stays pinned when it goes offline", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result, rerender } = renderHook(
    ({ online }) =>
      useAgentOptions(agents, "fast", {
        ...onlineStatus,
        machines: [{ ...onlineStatus.machines[1], online }],
      }),
    { initialProps: { online: true } },
  );
  rerender({ online: false });
  expect(result.current.agentOptionValues.sandbox_machine_id).toBe("this-mac");
});

test("restored cloud conversations stay cloud when a daemon reconnects", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result } = renderHook(() => useAgentOptions(agents, "fast"));
  act(() => result.current.restoreAgentOptions({ sandbox: "cloud" }));
  act(() => window.dispatchEvent(new Event(SANDBOX_ONLINE_CHANGED_EVENT)));
  expect(result.current.agentOptionValues.sandbox).toBe("cloud");
});

test("new conversations use an already online daemon, and reset old directory bindings", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result } = renderHook(() =>
    useAgentOptions(agents, "fast", onlineStatus),
  );
  expect(result.current.agentOptionValues.sandbox).toBe("local");
  act(() =>
    result.current.restoreAgentOptions({
      sandbox: "cloud",
      sandbox_workspace: "old",
    }),
  );
  act(() => result.current.resetAgentOptionDefaults());
  expect(result.current.agentOptionValues.sandbox).toBe("local");
  expect(result.current.agentOptionValues.sandbox_workspace).toBeUndefined();
});

test("project selection inherits its machine and directory only into the new draft", () => {
  const change = vi.fn();
  const setProject = vi.fn();
  const workspace = {
    id: "local-" + "a".repeat(32),
    machineId: "mac",
    path: "/repo",
  };
  const { result } = renderHook(() =>
    useWorkspaceOptionActions(null, change, setProject),
  );
  act(() => result.current.selectProject("project-1", workspace));
  expect(setProject).toHaveBeenCalledWith("project-1");
  expect(change.mock.calls).toEqual([
    ["sandbox", "local"],
    ["sandbox_machine_id", "mac"],
    ["sandbox_workspace", JSON.stringify(workspace)],
  ]);
});

test("changing agents preserves the workspace but resets agent-specific options", () => {
  const agents = [
    { id: "search", options: { depth: { default: 1 } } },
    { id: "team", options: { depth: { default: 2 } } },
  ] as unknown as AgentInfo[];
  const { result, rerender } = renderHook(
    ({ agent }) => useAgentOptions(agents, agent, onlineStatus),
    { initialProps: { agent: "search" } },
  );
  act(() => {
    result.current.handleToggleAgentOption("sandbox_machine_id", "remote-pc");
    result.current.handleToggleAgentOption(
      "sandbox_workspace",
      "selected-directory",
    );
    result.current.handleToggleAgentOption("depth", 9);
  });
  rerender({ agent: "team" });
  expect(result.current.agentOptionValues).toMatchObject({
    sandbox: "local",
    sandbox_machine_id: "remote-pc",
    sandbox_workspace: "selected-directory",
    depth: 2,
  });
  act(() => result.current.resetAgentOptionDefaults());
  expect(result.current.agentOptionValues.sandbox_workspace).toBeUndefined();
});

test("switching agents after restoring a chat keeps the latest workspace choice", () => {
  const agents = ["search", "team"].map((id) => ({
    id,
    options: {},
  })) as AgentInfo[];
  const { result, rerender } = renderHook(
    ({ agent }) => useAgentOptions(agents, agent, onlineStatus),
    { initialProps: { agent: "search" } },
  );
  act(() =>
    result.current.restoreAgentOptions({
      sandbox: "local",
      sandbox_workspace: "old",
    }),
  );
  act(() => result.current.handleToggleAgentOption("sandbox_workspace", "new"));
  rerender({ agent: "team" });
  expect(result.current.agentOptionValues.sandbox_workspace).toBe("new");
});

test("selecting the current machine keeps its directory without another save", () => {
  const agents = [{ id: "search", options: {} }] as AgentInfo[];
  const { result } = renderHook(() =>
    useAgentOptions(agents, "search", onlineStatus),
  );
  act(() =>
    result.current.restoreAgentOptions({
      sandbox: "local",
      sandbox_machine_id: "mac",
      sandbox_workspace: "selected-directory",
    }),
  );
  act(() => {
    expect(
      result.current.handleToggleAgentOption("sandbox_machine_id", "mac"),
    ).toEqual({});
  });
  expect(result.current.agentOptionValues.sandbox_workspace).toBe(
    "selected-directory",
  );
});

test("bound project drafts select a sandbox-capable agent and restore the binding across that switch", () => {
  const change = vi.fn();
  const restore = vi.fn();
  const select = vi.fn();
  const workspace = {
    id: "local-" + "a".repeat(32),
    machineId: "mac",
    path: "/repo",
  };
  const { result } = renderHook(() =>
    useWorkspaceOptionActions(null, change, vi.fn(), {
      agents: [
        { id: "fast", supports_sandbox: false },
        { id: "search", supports_sandbox: true },
      ] as AgentInfo[],
      currentAgent: "fast",
      switchAgent: select,
      restoreAgentOptions: restore,
    }),
  );
  act(() => result.current.selectProject("project-1", workspace));
  expect(select).toHaveBeenCalledWith("search");
  expect(restore).toHaveBeenCalledWith({
    sandbox: "local",
    sandbox_machine_id: "mac",
    sandbox_workspace: JSON.stringify(workspace),
  });
});
