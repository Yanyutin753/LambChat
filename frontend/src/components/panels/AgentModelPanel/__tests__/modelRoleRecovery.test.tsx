/** @vitest-environment jsdom */
import { useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { ModelSection } from "../ModelSection";
import { ModelPanel } from "../../ModelPanel/ModelPanel";
import { AgentModelPanel } from "../AgentModelPanel";
import { RolesModelTab } from "../../ModelPanel/tabs/RolesModelTab";
import type { Role } from "../../../../types";
import type { ModelConfig } from "../../../../services/api/model";

const api = vi.hoisted(() => ({
  getRoleModels: vi.fn(),
  updateRoleModels: vi.fn(),
  listRoles: vi.fn(),
  listModels: vi.fn(),
  toggleModel: vi.fn(),
  getCatalogConfig: vi.fn(),
  getRoleAgents: vi.fn(),
  listAgents: vi.fn(),
}));
vi.mock("../../../../services/api", () => ({
  agentConfigApi: api,
  roleApi: { list: api.listRoles },
  modelApi: { list: api.listModels, toggle: api.toggleModel },
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
const models = [
  {
    id: "one",
    value: "model-one",
    label: "One",
    description: "First model",
    enabled: true,
  },
  { id: "two", value: "model-two", label: "Two", enabled: true },
] as ModelConfig[];
afterEach(cleanup);
beforeEach(async () => {
  vi.clearAllMocks();
  await i18n.changeLanguage("en");
  api.listRoles.mockResolvedValue({ roles });
  api.listModels.mockResolvedValue({ models });
  api.getRoleModels.mockResolvedValue({
    configured: true,
    allowed_models: ["one"],
  });
  api.updateRoleModels.mockResolvedValue({});
  const agents = [
    { id: "one", name: "Agent One", description: "Agent", enabled: true },
  ];
  api.getCatalogConfig.mockResolvedValue({ agents });
  api.listAgents.mockResolvedValue({ agents });
  api.getRoleAgents.mockResolvedValue({ allowed_agents: ["one"] });
});

test.each([
  ["embedded", ModelSection],
  ["standalone", ModelPanel],
])(
  "%s blocks editing when a role model read fails and retries without losing focus",
  async (_, Component) => {
    api.getRoleModels.mockRejectedValueOnce(
      new Error("Model assignment unavailable"),
    );
    render(<Component />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Model assignment unavailable",
    );
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Select all" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("checkbox", { name: "One" });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.activeElement).not.toBe(document.body);
    expect(api.updateRoleModels).not.toHaveBeenCalled();
  },
);
test.each([
  [false, true],
  [true, false],
])(
  "configured=%s preserves the server default-versus-empty distinction",
  async (configured, checked) => {
    api.getRoleModels.mockResolvedValue({ configured, allowed_models: [] });
    render(<ModelSection />);
    expect(
      (
        (await screen.findByRole("checkbox", {
          name: "One",
        })) as HTMLInputElement
      ).checked,
    ).toBe(checked);
  },
);
test("refresh after removing all models does not retain stale model checkboxes", async () => {
  render(<ModelPanel />);
  await screen.findByRole("checkbox", { name: "One" });
  api.listModels.mockResolvedValue({ models: [] });
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() =>
    expect(
      screen
        .getAllByText("No models configured")
        .some((el) => !el.closest("[hidden]")),
    ).toBe(true),
  );
  expect(screen.queryByRole("checkbox")).toBeNull();
});
function Harness({
  update,
}: {
  update: (role: string, ids: string[]) => Promise<void>;
}) {
  const [map, setMap] = useState({ a: ["one"], b: ["one"] });
  return (
    <RolesModelTab
      roles={roles}
      roleModelsMap={map}
      availableModels={models as Required<ModelConfig>[]}
      isLoading={false}
      onUpdate={async (id, ids) => {
        await update(id, ids);
        setMap((prev) => ({ ...prev, [id]: ids }));
      }}
    />
  );
}
async function chooseRole(name: string) {
  fireEvent.click(screen.getByRole("button", { name: "Select a role" }));
  fireEvent.click(await screen.findByRole("option", { name }));
}
test("saving one role preserves another role draft and keeps focus stable", async () => {
  const update = vi.fn().mockResolvedValue(undefined);
  render(<Harness update={update} />);
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
test("failed model assignment save stays visible and preserves the draft for retry", async () => {
  const update = vi
    .fn()
    .mockRejectedValueOnce(new Error("Write unavailable"))
    .mockResolvedValue(undefined);
  render(<Harness update={update} />);
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
test("pending save locks role, bulk actions, and checkboxes", async () => {
  let finish!: () => void;
  render(
    <Harness
      update={() =>
        new Promise<void>((resolve) => {
          finish = resolve;
        })
      }
    />,
  );
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  for (const name of ["Select a role", "Select all", "Clear all"])
    expect(
      (screen.getByRole("button", { name }) as HTMLButtonElement).disabled,
    ).toBe(true);
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement)
      .disabled,
  ).toBe(true);
  await act(async () => {
    finish();
  });
});
test("model description action is separate from the checkbox label", () => {
  render(<Harness update={vi.fn()} />);
  const expand = screen.getByRole("button", { name: "Expand One" });
  expect(expand.closest("label")).toBeNull();
  fireEvent.click(expand);
  expect(screen.getByText("First model")).toBeTruthy();
  expect(
    (screen.getByRole("checkbox", { name: "One" }) as HTMLInputElement).checked,
  ).toBe(true);
});
test("empty roles explain the absence of assignment controls", () => {
  render(
    <RolesModelTab
      roles={[]}
      roleModelsMap={{}}
      availableModels={models as Required<ModelConfig>[]}
      onUpdate={vi.fn()}
      isLoading={false}
    />,
  );
  expect(screen.getByText("No roles yet")).toBeTruthy();
});
test("model sub-section switch keeps assignment drafts and exposes pressed state", async () => {
  render(<ModelSection />);
  await screen.findByRole("checkbox", { name: "One" });
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  fireEvent.click(screen.getByRole("button", { name: "Model Config" }));
  expect(
    screen
      .getByRole("button", { name: "Model Config" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
  fireEvent.click(screen.getByRole("button", { name: "Models", exact: true }));
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement).checked,
  ).toBe(true);
});
test("top section switches keep both drafts and load models only on first visit", async () => {
  render(<AgentModelPanel />);
  const header = document.querySelector(".panel-header") as HTMLElement;
  await screen.findByRole("switch", { name: "Disable Agent One" });
  expect(api.listModels).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("switch", { name: "Disable Agent One" }));
  fireEvent.click(within(header).getByRole("button", { name: "Models" }));
  await screen.findByRole("checkbox", { name: "Two" });
  fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
  fireEvent.click(within(header).getByRole("button", { name: "Assistants" }));
  expect(
    screen
      .getByRole("switch", { name: "Enable Agent One" })
      .getAttribute("aria-checked"),
  ).toBe("false");
  fireEvent.click(within(header).getByRole("button", { name: "Models" }));
  expect(
    (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement).checked,
  ).toBe(true);
  expect(api.listModels).toHaveBeenCalledTimes(1);
});

test("bulk selection and page changes preserve assignments across the whole model list", async () => {
  const allModels = Array.from({ length: 21 }, (_, i) => ({
    id: `m-${i}`,
    value: `model-${i}`,
    label: `Model ${i}`,
  }));
  const update = vi.fn().mockResolvedValue(undefined);
  render(
    <RolesModelTab
      roles={roles}
      roleModelsMap={{ a: [] }}
      availableModels={allModels}
      onUpdate={update}
      isLoading={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Select all" }));
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(
    (screen.getByRole("checkbox", { name: "Model 20" }) as HTMLInputElement)
      .checked,
  ).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: "Model 20" }));
  fireEvent.click(screen.getByRole("button", { name: "Previous" }));
  expect(
    (screen.getByRole("checkbox", { name: "Model 0" }) as HTMLInputElement)
      .checked,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      "a",
      allModels.slice(0, 20).map((m) => m.id),
    ),
  );
});

test.each(["refresh", "configuration update"])(
  "%s preserves a role draft instead of remounting the assignment tab",
  async (operation) => {
    render(<ModelPanel />);
    await screen.findByRole("checkbox", { name: "Two" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
    let finishRefresh!: (result: { models: ModelConfig[] }) => void;
    api.listModels.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishRefresh = resolve;
        }),
    );
    if (operation === "refresh") {
      const refresh = screen.getByRole("button", { name: "Refresh" });
      refresh.focus();
      fireEvent.click(refresh);
    } else {
      api.toggleModel.mockResolvedValue({});
      fireEvent.click(screen.getByRole("button", { name: "Model Config" }));
      const toggle = screen.getAllByRole("switch", { name: "Disable" })[0];
      toggle.focus();
      fireEvent.click(toggle);
    }
    await waitFor(() => expect(api.listModels).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("status")).toBeTruthy();
    expect(document.querySelector("[inert]")).toBeTruthy();
    expect(document.activeElement).not.toBe(document.body);
    await act(async () => {
      finishRefresh({ models });
    });
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    if (operation === "configuration update")
      fireEvent.click(
        screen.getByRole("button", { name: "Models", exact: true }),
      );
    expect(
      (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(document.activeElement).not.toBe(document.body);
  },
);

test.each([
  ["embedded", ModelSection],
  ["standalone", ModelPanel],
])(
  "%s retains a draft through a failed background read and retry",
  async (_, Component) => {
    render(<Component />);
    await screen.findByRole("checkbox", { name: "Two" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Two" }));
    fireEvent.click(screen.getByRole("button", { name: "Model Config" }));
    api.toggleModel.mockResolvedValue({});
    api.getRoleModels.mockRejectedValueOnce(
      new Error("Assignment refresh failed"),
    );
    const toggle = screen.getAllByRole("switch", { name: "Disable" })[0];
    toggle.focus();
    fireEvent.click(toggle);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Assignment refresh failed",
    );
    expect(screen.queryByRole("checkbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    fireEvent.click(
      screen.getByRole("button", { name: "Models", exact: true }),
    );
    expect(
      (screen.getByRole("checkbox", { name: "Two" }) as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(api.updateRoleModels).not.toHaveBeenCalled();
  },
);
