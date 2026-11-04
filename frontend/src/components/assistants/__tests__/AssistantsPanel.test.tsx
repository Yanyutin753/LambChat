/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AssistantsPanel } from "../AssistantsPanel";

const { api, navigate, canWrite, t } = vi.hoisted(() => ({
  api: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    get: vi.fn(),
    openConversation: vi.fn(),
  },
  navigate: vi.fn(),
  canWrite: { value: true },
  t: (key: string) => key,
}));
vi.mock("../../../services/api/session", () => ({
  sessionApi: { cancel: vi.fn() },
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("../../../services/api/model", () => ({
  modelApi: { listAvailable: async () => ({ models: [] }) },
}));
vi.mock("../../../services/api/team", () => ({
  teamApi: {
    list: async () => ({
      teams: [{ id: "team-1", name: "Review team" }],
      total: 1,
    }),
  },
}));
vi.mock("../../../services/api/project", () => ({
  projectApi: { list: async () => [] },
}));
vi.mock("../../../services/api/personaPreset", () => ({
  personaPresetApi: { list: async () => ({ presets: [], total: 0 }) },
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    hasPermission: (permission: string) =>
      permission !== "chat:write" || canWrite.value,
  }),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useParams: () => ({}),
  useLocation: () => ({ pathname: "/assistants" }),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t }),
}));

const helper = {
  id: "helper",
  session_id: "thread",
  name: "Researcher",
  instructions: "Verify sources",
  revision: 4,
  status: "active",
  model_id: null,
  persona_preset_id: null,
  team_id: null,
  memory_mode: "private",
  project_id: null,
  sandbox: null,
  workspace: null,
};
beforeEach(() => {
  canWrite.value = true;
  api.list.mockResolvedValue({ assistants: [helper], total: 1 });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test("opening an assistant resolves its stable conversation through the server", async () => {
  api.openConversation.mockResolvedValue({ id: "stable-conversation" });
  render(<AssistantsPanel />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.open" }),
  );
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/chat/stable-conversation"),
  );
  expect(api.openConversation).toHaveBeenCalledWith("helper");
});

test("a failed load offers retry without claiming the assistant list is empty", async () => {
  api.list
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ assistants: [], total: 0 });
  render(<AssistantsPanel />);
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  expect(screen.queryByText("assistants.empty")).toBeNull();
  fireEvent.click(screen.getAllByRole("button", { name: "common.refresh" })[0]);
  expect(await screen.findByText("assistants.empty")).toBeInTheDocument();
});

test("creating an assistant saves real configuration and closes only after success", async () => {
  api.create
    .mockRejectedValueOnce(new Error("not saved"))
    .mockResolvedValueOnce(helper);
  render(<AssistantsPanel />);
  fireEvent.click(
    screen.getAllByRole("button", { name: "assistants.create" })[0],
  );
  fireEvent.change(
    await screen.findByRole("textbox", { name: /assistants.name/ }),
    { target: { value: "  Researcher  " } },
  );
  fireEvent.change(screen.getByLabelText("assistants.instructions"), {
    target: { value: "Verify sources" },
  });
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("not saved");
  expect(screen.getByRole("textbox", { name: /assistants.name/ })).toHaveValue(
    "  Researcher  ",
  );
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(api.create).toHaveBeenLastCalledWith({
    name: "Researcher",
    instructions: "Verify sources",
    model_id: null,
    persona_preset_id: null,
    team_id: null,
    memory_mode: "private",
    project_id: null,
    sandbox: null,
    workspace: null,
  });
});

test("read-only users can inspect assistants without mutation controls", async () => {
  canWrite.value = false;
  render(<AssistantsPanel />);
  expect(await screen.findByText("Researcher")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "assistants.create" }),
  ).toBeNull();
  expect(screen.queryByRole("button", { name: "assistants.open" })).toBeNull();
});

test("assistant configuration can select an owned collaboration team", async () => {
  api.create.mockResolvedValue(helper);
  render(<AssistantsPanel />);
  fireEvent.click(
    screen.getAllByRole("button", { name: "assistants.create" })[0],
  );
  fireEvent.change(
    await screen.findByRole("textbox", { name: /assistants.name/ }),
    { target: { value: "Coordinator" } },
  );
  const picker = await screen.findByRole("button", { name: "assistants.team" });
  await waitFor(() => expect(picker).not.toBeDisabled());
  fireEvent.click(picker);
  fireEvent.click(await screen.findByRole("option", { name: "Review team" }));
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() => expect(api.create).toHaveBeenCalled());
  expect(api.create.mock.calls[0][0].team_id).toBe("team-1");
  expect(api.create.mock.calls[0][0].persona_preset_id).toBeNull();
});

test("pausing an assistant preserves its explicit shared memory choice", async () => {
  api.list.mockResolvedValue({
    assistants: [{ ...helper, memory_mode: "project", project_id: "project" }],
    total: 1,
  });
  api.update.mockResolvedValue(helper);
  render(<AssistantsPanel />);
  fireEvent.click(
    await screen.findByRole("button", { name: "common.moreOptions" }),
  );
  fireEvent.click(
    await screen.findByRole("menuitem", { name: "assistants.pause" }),
  );
  await waitFor(() => expect(api.update).toHaveBeenCalled());
  expect(api.update.mock.calls[0][1].memory_mode).toBe("project");
});

test("assistant navigation wraps in the card body while status and menu stay in the footer", async () => {
  render(<AssistantsPanel />);
  const open = await screen.findByRole("button", { name: "assistants.open" });
  expect(open.closest(".scb__footer")).toBeNull();
  expect(open.parentElement).toHaveClass("flex-wrap");
  expect(
    screen.getByText("assistants.active").closest(".scb__footer"),
  ).not.toBeNull();
});
