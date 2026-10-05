/** @vitest-environment jsdom */
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { ChannelRunConfigFields } from "../ChannelRunConfigFields";
import type { ChannelRuntimeConfig } from "../../../../types/channel";

vi.mock("../../../../services/api/project", () => ({ projectApi: { list: vi.fn(async () => [
  { id: "project-local", name: "Local source", type: "custom", workspace: { id: "workspace", machineId: "machine-a", path: "/repo" } },
  { id: "project-plain", name: "Research", type: "custom" },
]) } }));
vi.mock("../../../../hooks/useSandboxStatus", () => ({ useSandboxStatus: () => ({
  machines: [{ machine_id: "machine-a", name: "Laptop", online: true }], statusError: null,
}) }));
afterEach(cleanup);

function Harness() {
  const [value, setValue] = useState<ChannelRuntimeConfig>({ sandbox: "cloud" });
  const [project, setProject] = useState<string | null>(null);
  const [envText, setEnvText] = useState("TOKEN=***");
  return <><ChannelRunConfigFields value={value} onChange={setValue} projectId={project}
    onProjectChange={setProject} envText={envText} onEnvTextChange={setEnvText} />
    <output data-testid="runtime">{JSON.stringify(value)}</output></>;
}

test("linked project forces its local machine and directory while clearing it unlocks choices", async () => {
  render(<Harness />);
  const project = await screen.findByLabelText(i18n.t("channel.runtime.project"));
  await screen.findByRole("option", { name: "Local source" });
  fireEvent.change(project, { target: { value: "project-local" } });
  const sandbox = screen.getByLabelText(i18n.t("channel.runtime.sandbox"));
  await waitFor(() => expect(sandbox).toHaveValue("local"));
  expect(sandbox).toBeDisabled();
  expect(screen.getByLabelText(i18n.t("channel.runtime.machine"))).toHaveValue("machine-a");
  expect(screen.getByText(/\/repo/)).toBeVisible();
  expect(JSON.parse(screen.getByTestId("runtime").textContent!)).toMatchObject({ sandbox: "local", sandbox_machine_id: "machine-a" });
  fireEvent.change(project, { target: { value: "" } });
  expect(sandbox).not.toBeDisabled();
  fireEvent.change(sandbox, { target: { value: "cloud" } });
  expect(sandbox).toHaveValue("cloud");
});

test("reset clears environment overrides and returns common parameters to inherited defaults", async () => {
  render(<Harness />);
  await screen.findByRole("option", { name: "Local source" });
  expect(screen.getByLabelText(i18n.t("channel.runtime.env"))).toHaveValue("TOKEN=***");
  fireEvent.click(screen.getByRole("button", { name: i18n.t("channel.runtime.reset") }));
  expect(screen.getByLabelText(i18n.t("channel.runtime.env"))).toHaveValue("");
  expect(screen.getByLabelText(i18n.t("channel.runtime.sandbox"))).toHaveValue("default");
  expect(screen.getByLabelText(i18n.t("channel.runtime.thinking"))).toHaveValue("");
});
