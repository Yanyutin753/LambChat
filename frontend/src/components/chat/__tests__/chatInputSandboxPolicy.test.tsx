/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ChatInputSelectors } from "../ChatInputSelectors";

const state = vi.hoisted(() => ({
  user: { id: "user-1", metadata: { sandboxCloudConfirmPolicy: "none" } },
  refreshUser: vi.fn(),
  metadata: vi.fn(),
  machinePolicy: vi.fn(),
  refreshSandbox: vi.fn(),
  error: vi.fn(),
  machines: [
    { machine_id: "mac", name: "My Mac", online: true, confirm_policy: "all" },
    { machine_id: "pc", name: "My PC", online: true, confirm_policy: "commands" },
  ],
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-hot-toast", () => ({ toast: { success: vi.fn(), error: state.error } }));
vi.mock("../../../hooks/useAuth", () => ({ useAuth: () => state }));
vi.mock("../../../hooks/useSandboxStatus", () => ({
  useSandboxStatus: () => ({ online: true, machines: state.machines, defaultMachineId: "mac", currentMachineId: null }),
  notifySandboxStatusRefresh: state.refreshSandbox,
}));
vi.mock("../../../services/tauri/sandboxShell", () => ({ isShellAvailable: () => false, writeConfirmPolicy: vi.fn() }));
vi.mock("../../../services/api", () => ({ authApi: { updateMetadata: state.metadata } }));
vi.mock("../../../services/api/sandbox", () => ({ sandboxApiMachines: { updateConfirmPolicy: state.machinePolicy } }));
vi.mock("../../selectors/AgentModeSelector", () => ({ AgentModeSelector: () => null }));
vi.mock("../../selectors/ToolSelector", () => ({ ToolSelector: () => null }));
vi.mock("../../selectors/SkillSelector", () => ({ SkillSelector: () => null }));
vi.mock("../../persona/PersonaPresetSelector", () => ({ PersonaPresetSelector: () => null }));
vi.mock("../../team/TeamPickerModal", () => ({ TeamPickerModal: () => null }));

const option = {
  type: "select" as const, label: "Sandbox", default: "cloud",
  options: [{ value: "cloud", label: "Cloud" }, { value: "local", label: "Local" }],
};
function panel(sandbox = "cloud", machine = "mac") {
  return <ChatInputSelectors activePanel="sandbox" onActivePanelChange={vi.fn()} agentOptions={{ sandbox: option }} agentOptionValues={{ sandbox, sandbox_machine_id: machine }} onToggleAgentOption={vi.fn()} />;
}
beforeEach(() => {
  vi.clearAllMocks();
  state.metadata.mockResolvedValue(state.user);
  state.machinePolicy.mockResolvedValue(undefined);
  state.refreshUser.mockResolvedValue(undefined);
});
afterEach(cleanup);

function choosePolicy(policy: string) {
  fireEvent.click(screen.getByRole("button", { name: "agentOptions.sandboxPolicy.section" }));
  fireEvent.click(screen.getByRole("option", { name: `agentOptions.sandboxPolicy.${policy}` }));
}
function selectedPolicy(policy: string) {
  return screen.getByRole("button", {
    name: "agentOptions.sandboxPolicy.section",
    description: `agentOptions.sandboxPolicy.${policy}`,
  });
}

test("cloud shows its policy without personal devices or local offline guidance", () => {
  render(panel());
  expect(selectedPolicy("none")).toBeInTheDocument();
  expect(document.querySelector("[data-sandbox-machine-section]")).toBeNull();
  expect(document.querySelector("[data-sandbox-download-entry]")).toBeNull();
});

test("cloud saves account policy without writing any personal computer policy", async () => {
  render(panel());
  choosePolicy("all");
  await waitFor(() => expect(state.metadata).toHaveBeenCalledWith({ sandboxCloudConfirmPolicy: "all" }));
  await waitFor(() => expect(selectedPolicy("all")).toBeInTheDocument());
  expect(state.machinePolicy).not.toHaveBeenCalled();
});

test("failed cloud save keeps the saved policy and offers retry", async () => {
  state.metadata.mockRejectedValueOnce(new Error("offline"));
  render(panel());
  choosePolicy("all");
  await screen.findByText("agentOptions.sandboxPolicy.updateFailed");
  expect(selectedPolicy("none")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  await waitFor(() => expect(state.metadata).toHaveBeenCalledTimes(2));
});

test("local automatic selection edits the online default computer policy", async () => {
  render(panel("local", ""));
  choosePolicy("none");
  await waitFor(() => expect(state.machinePolicy).toHaveBeenCalledWith("mac", "none"));
  expect(state.metadata).not.toHaveBeenCalled();
});

test("switching machines and returning to cloud keeps policies separate", async () => {
  const view = render(panel("local"));
  choosePolicy("none");
  await waitFor(() => expect(selectedPolicy("none")).toBeInTheDocument());
  view.rerender(panel("local", "pc"));
  expect(selectedPolicy("commands")).toBeInTheDocument();
  view.rerender(panel("cloud", "pc"));
  expect(selectedPolicy("none")).toBeInTheDocument();
  expect(document.querySelector("[data-sandbox-machine-section]")).toBeNull();
});
