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
import { useState } from "react";
import i18n from "../../../../i18n";
import { AgentSection } from "../AgentSection";
import { AgentConfigPanel } from "../../AgentPanel/AgentConfigPanel";
import { RolesAgentTab } from "../../AgentPanel/tabs/RolesAgentTab";
import { RoleSelector } from "../../AgentPanel/shared/RoleSelector";
import type { AgentInfo, Role } from "../../../../types";

const api = vi.hoisted(() => ({
  getCatalogConfig: vi.fn(),
  getRoleAgents: vi.fn(),
  updateRoleAgents: vi.fn(),
  listRoles: vi.fn(),
  listAgents: vi.fn(),
}));
vi.mock("../../../../services/api", () => ({
  agentConfigApi: api,
  roleApi: { list: api.listRoles },
  agentApi: { list: api.listAgents },
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
const roles = [
  { id: "a", name: "Alpha" },
  { id: "b", name: "Beta" },
] as Role[];
const agents = [
  {
    id: "one",
    name: "One",
    description: "First assistant",
    version: "",
    icon: "Bot",
  },
  {
    id: "two",
    name: "Two",
    description: "Second assistant",
    version: "",
    icon: "Bot",
  },
] as AgentInfo[];
afterEach(cleanup);
beforeEach(async () => {
  vi.clearAllMocks();
  await i18n.changeLanguage("en");
  api.getCatalogConfig.mockResolvedValue({
    agents: agents.map((a) => ({ ...a, enabled: true })),
  });
  api.listRoles.mockResolvedValue({ roles });
  api.listAgents.mockResolvedValue({ agents });
  api.getRoleAgents.mockResolvedValue({ allowed_agents: ["one"] });
  api.updateRoleAgents.mockResolvedValue({});
});

test.each([
  ["embedded", AgentSection],
  ["standalone", AgentConfigPanel],
])(
  "%s blocks editing when a role assignment read fails and recovers with focus",
  async (_, Component) => {
    api.getRoleAgents.mockRejectedValueOnce(
      new Error("Assignment unavailable"),
    );
    render(<Component />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Assignment unavailable",
    );
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("switch", { name: "Disable One" });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.activeElement).not.toBe(document.body);
    expect(api.updateRoleAgents).not.toHaveBeenCalled();
  },
);

test("section switches report selection and retain role drafts", async () => {
  render(<AgentSection />);
  await screen.findByRole("switch", { name: "Disable One" });
  fireEvent.click(screen.getByRole("button", { name: "Role Assignments" }));
  expect(
    screen
      .getByRole("button", { name: "Role Assignments" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  fireEvent.click(screen.getByRole("button", { name: "Global" }));
  fireEvent.click(screen.getByRole("button", { name: "Role Assignments" }));
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement).checked,
  ).toBe(true);
});

test("changing language does not reload or discard assignments", async () => {
  render(<AgentSection />);
  await screen.findByRole("switch", { name: "Disable One" });
  fireEvent.click(screen.getByRole("button", { name: "Role Assignments" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  await act(async () => {
    await i18n.changeLanguage("zh");
  });
  expect(api.getCatalogConfig).toHaveBeenCalledTimes(1);
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement).checked,
  ).toBe(true);
});

function RoleHarness({
  update,
}: {
  update: (roleId: string, ids: string[]) => Promise<void>;
}) {
  const [map, setMap] = useState({ a: ["one"], b: ["one"] });
  return (
    <RolesAgentTab
      roles={roles}
      roleAgentsMap={map}
      availableAgents={agents}
      isLoading={false}
      onUpdate={async (id, ids) => {
        await update(id, ids);
        setMap((prev) => ({ ...prev, [id]: ids }));
      }}
    />
  );
}
async function chooseRole(name: string) {
  fireEvent.click(
    screen.getByRole("button", { name: /Select a role|Alpha|Beta/ }),
  );
  fireEvent.click(await screen.findByRole("option", { name }));
}
test("saving Alpha preserves an unsaved Beta draft and keeps focus connected", async () => {
  const update = vi.fn().mockResolvedValue(undefined);
  render(<RoleHarness update={update} />);
  await chooseRole("Beta");
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  await chooseRole("Alpha");
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(update).toHaveBeenCalledWith("a", ["one", "two"]));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull(),
  );
  expect(document.activeElement).not.toBe(document.body);
  await chooseRole("Beta");
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement).checked,
  ).toBe(true);
});
test("failed save remains visible and preserves the draft for retry", async () => {
  const update = vi
    .fn()
    .mockRejectedValueOnce(new Error("Write unavailable"))
    .mockResolvedValue(undefined);
  render(<RoleHarness update={update} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Write unavailable",
  );
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement).checked,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(update).toHaveBeenCalledTimes(2);
});
test("pending save locks selection until its draft is committed", async () => {
  let finish!: () => void;
  const update = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  render(<RoleHarness update={update} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement)
      .disabled,
  ).toBe(true);
  expect(
    (
      screen.getByRole("button", {
        name: /Select a role|Alpha/,
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await act(async () => {
    finish();
  });
});
test("role selector supports keyboard opening and Escape focus return", () => {
  render(
    <RoleSelector roles={roles} selectedRoleId="a" onSelectRole={vi.fn()} />,
  );
  const trigger = screen.getByRole("button", { name: /Select a role|Alpha/ });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  expect(
    screen.getByRole("button", { name: "Select a role", description: "Alpha" }),
  ).toBe(trigger);
  const selected = screen.getByRole("option", { name: "Alpha" });
  expect(document.activeElement).toBe(selected);
  fireEvent.keyDown(selected, { key: "Escape" });
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});
test("empty roles explain why there are no assignment controls", () => {
  render(
    <RolesAgentTab
      roles={[]}
      roleAgentsMap={{}}
      availableAgents={agents}
      isLoading={false}
      onUpdate={vi.fn()}
    />,
  );
  expect(screen.getByText("No roles yet")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Select a role/ })).toBeNull();
});
