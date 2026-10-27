/** @vitest-environment jsdom */
import { useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ChatInput } from "../ChatInput";
import { workspaceOptionPatch } from "../workspaceSelection";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("../ComposerUsageChip", () => ({
  ComposerUsageChip: () => null,
}));

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../../hooks/useFileUpload", () => ({
  useFileUpload: () => ({
    uploadFiles: vi.fn(),
    uploadFile: vi.fn(),
    uploadLimits: null,
    validateCount: () => true,
    cancelUpload: vi.fn(),
  }),
}));
vi.mock("../../../hooks/useSandboxStatus", () => ({
  useSandboxStatus: () => ({
    currentMachineId: "m1",
    defaultMachineId: "m1",
    machines: [{ machine_id: "m1", online: true }],
  }),
}));
vi.mock("../../../services/tauri/sandboxShell", () => ({
  invokeInShell: invoke,
  isShellAvailable: () => true,
}));
vi.mock("../ChatInputSelectors", () => ({ ChatInputSelectors: () => null }));

const picked = {
  id: `local-${"a".repeat(32)}`,
  machineId: "m1",
  path: "/repo",
};
const agents = [
  {
    id: "search",
    name: "Search",
    description: "",
    version: "1",
    supports_sandbox: true,
  },
];
function Composer({
  onSend,
  input = "List the files",
}: {
  onSend: ReturnType<typeof vi.fn>;
  input?: string;
}) {
  const [values, setValues] = useState<
    Record<string, string | boolean | number>
  >({
    sandbox: "local",
    sandbox_machine_id: "m1",
  });
  return (
    <ChatInput
      onSend={onSend}
      onStop={vi.fn()}
      isLoading={false}
      pendingInput={input}
      currentAgent="search"
      agents={agents}
      agentOptionValues={values}
      onToggleAgentOption={(key, value) =>
        setValues((old) => ({ ...old, ...workspaceOptionPatch(key, value) }))
      }
    />
  );
}
beforeEach(() => {
  localStorage.clear();
  invoke.mockReset();
});

test.each(["pause", "resume", "clear"])(
  "/goal %s preserves the existing goal workspace",
  async (action) => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} input={`/goal ${action}`} />);
    const editor = await screen.findByRole("textbox");
    await waitFor(() => expect(editor).toHaveTextContent(`/goal ${action}`));
    await act(async () => {
      fireEvent.submit(editor.closest("form")!);
    });
    expect(invoke).not.toHaveBeenCalled();
    expect(onSend).toHaveBeenCalled();
  },
);
afterEach(cleanup);

test("choosing a workspace preserves the draft and the next submission uses that directory", async () => {
  invoke.mockResolvedValue(picked);
  const onSend = vi.fn();
  render(<Composer onSend={onSend} />);
  const editor = await screen.findByRole("textbox");
  await waitFor(() => expect(editor).toHaveTextContent("List the files"));
  await act(async () => {
    fireEvent.submit(editor.closest("form")!);
  });
  await screen.findByText("repo");
  expect(onSend).not.toHaveBeenCalled();
  expect(editor).toHaveTextContent("List the files");
  await act(async () => {
    fireEvent.submit(editor.closest("form")!);
  });
  expect(onSend).toHaveBeenCalledWith(
    "List the files",
    {
      sandbox: "local",
      sandbox_machine_id: "m1",
      sandbox_workspace: JSON.stringify(picked),
    },
    [],
    undefined,
    expect.any(Object),
  );
});

test("cancelling the directory picker keeps the draft and does not start an independent workspace", async () => {
  invoke.mockResolvedValue(null);
  const onSend = vi.fn();
  render(<Composer onSend={onSend} />);
  const editor = await screen.findByRole("textbox");
  await waitFor(() => expect(editor).toHaveTextContent("List the files"));
  await act(async () => {
    fireEvent.submit(editor.closest("form")!);
  });
  await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1));
  expect(onSend).not.toHaveBeenCalled();
  expect(editor).toHaveTextContent("List the files");
});

test("local composer offers directory selection directly above the input", async () => {
  invoke.mockResolvedValue(picked);
  render(<Composer onSend={vi.fn()} />);
  const choose = await screen.findByRole("button", {
    name: "Choose working directory",
  });
  expect(choose.closest(".composer-workspace-strip")).not.toBeNull();
  fireEvent.click(choose);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("sandbox_pick_workspace", {
      title: "Choose working directory",
    }),
  );
  expect(
    await screen.findByRole("button", {
      name: "Choose working directory: /repo",
    }),
  ).toHaveTextContent("repo");
});
