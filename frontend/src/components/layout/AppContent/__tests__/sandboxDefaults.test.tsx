/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useWorkspaceOptionActions } from "../sessionToggleCallbacks";
import type { AgentInfo } from "../../../../types";
import {
  useAgentOptions,
  SANDBOX_ONLINE_CHANGED_EVENT,
} from "../useAgentOptions";

test("restored cloud conversations stay cloud when a daemon reconnects", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result } = renderHook(() => useAgentOptions(agents, "fast"));
  act(() => result.current.restoreAgentOptions({ sandbox: "cloud" }));
  act(() => window.dispatchEvent(new Event(SANDBOX_ONLINE_CHANGED_EVENT)));
  expect(result.current.agentOptionValues.sandbox).toBe("cloud");
});

test("new conversations use an already online daemon, and reset old directory bindings", () => {
  const agents = [{ id: "fast", options: {} }] as AgentInfo[];
  const { result } = renderHook(() => useAgentOptions(agents, "fast", true));
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
