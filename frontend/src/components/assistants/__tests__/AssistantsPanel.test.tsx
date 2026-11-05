/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AssistantsPanel } from "../AssistantsPanel";

const { api, profiles, navigate, canWrite, route, t } = vi.hoisted(() => ({
  api: {
    chief: vi.fn(),
    members: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    get: vi.fn(),
    openConversation: vi.fn(),
    forConversation: vi.fn(),
    tasks: vi.fn(),
    task: vi.fn(),
    reviewTask: vi.fn(),
  },
  profiles: { persona: vi.fn(), team: vi.fn(), allowed: true },
  navigate: vi.fn(),
  route: {
    assistantId: undefined as string | undefined,
    view: undefined as string | undefined,
    sessionId: undefined as string | undefined,
  },
  canWrite: { value: true },
  t: (key: string) => key,
}));
vi.mock("../../common/AgentAvatar", () => ({
  AgentAvatar: ({ avatar, seed }: { avatar?: string; seed?: string }) => (
    <span
      data-testid={seed === "Chief" ? "chief-avatar" : "assistant-avatar"}
      data-avatar={avatar}
      data-seed={seed}
    />
  ),
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
    get: profiles.team,
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
  personaPresetApi: {
    get: profiles.persona,
    list: async () => ({ presets: [], total: 0 }),
  },
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    hasPermission: (permission: string) =>
      ["persona_preset:read", "team:read"].includes(permission)
        ? profiles.allowed
        : permission !== "chat:write" || canWrite.value,
  }),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useParams: () => route,
  useLocation: () => ({
    pathname: route.assistantId
      ? `/assistants/${route.assistantId}/${route.view || ""}`
      : "/assistants",
  }),
  useSearchParams: () => [new URLSearchParams()],
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t }),
}));

vi.mock("../../layout/AppContent/ChatAppContent", () => ({
  ChatAppContent: () => <div>Real chat workspace</div>,
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
  profiles.allowed = true;
  profiles.persona.mockResolvedValue({
    name: "Research role",
    avatar: "/role.png",
  });
  profiles.team.mockResolvedValue({ name: "Review team", avatar: "/team.png" });
  route.assistantId = undefined;
  route.view = undefined;
  route.sessionId = undefined;
  api.get.mockResolvedValue(helper);
  api.openConversation.mockResolvedValue({ id: "thread" });
  api.tasks.mockResolvedValue({ tasks: [], total: 0 });
  api.list.mockResolvedValue({ assistants: [helper], total: 1 });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test("selecting an assistant opens its dedicated workspace", async () => {
  render(<AssistantsPanel />);
  fireEvent.click(await screen.findByRole("button", { name: /Researcher/ }));
  expect(navigate).toHaveBeenCalledWith("/assistants/helper");
});

test("an assistant deep link resolves its canonical conversation inside the workspace", async () => {
  route.assistantId = "helper";
  render(<AssistantsPanel />);
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/assistants/helper/chat/thread", {
      replace: true,
    }),
  );
});

test("tasks are a page region with no modal and keep workspace navigation", async () => {
  route.assistantId = "helper";
  route.view = "tasks";
  render(<AssistantsPanel />);
  expect(
    await screen.findByRole("button", { name: "assistants.newTask" }),
  ).toBeVisible();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(
    screen.queryByRole("navigation", {
      name: "assistants.workspaceNavigation",
    }),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.moreOptions" }));
  expect(
    await screen.findByRole("menuitem", { name: "assistants.workRecords" }),
  ).toBeVisible();
});

test("a session from a different assistant never renders in the selected workspace", async () => {
  route.assistantId = "helper";
  route.view = "chat";
  route.sessionId = "foreign";
  api.forConversation.mockResolvedValue({ ...helper, id: "other" });
  render(<AssistantsPanel />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "assistants.conversationMismatch",
  );
  expect(screen.queryByText("Real chat workspace")).toBeNull();
});

test("assistant pagination does not reset during a page request", async () => {
  api.list.mockImplementation((skip) =>
    Promise.resolve({
      total: 21,
      assistants: [{ ...helper, name: skip ? "Second page" : "First page" }],
    }),
  );
  render(<AssistantsPanel />);
  await screen.findByRole("button", { name: /First page/ });
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  expect(
    await screen.findByRole("button", { name: /Second page/ }),
  ).toBeVisible();
  expect(api.list).toHaveBeenLastCalledWith(20, 20, false);
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
    screen.getAllByRole("button", { name: "assistants.newChat" })[0],
  );
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "assistants.create",
    }),
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
    kind: "assistant",
    member_ids: [],
    leader_id: null,
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
    screen.getAllByRole("button", { name: "assistants.newChat" })[0],
  );
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "assistants.create",
    }),
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
  route.assistantId = "helper";
  route.view = "tasks";
  api.get.mockResolvedValue({
    ...helper,
    memory_mode: "project",
    project_id: "project",
  });
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

test("read-only users can open saved conversations without creating one", async () => {
  canWrite.value = false;
  route.assistantId = "helper";
  render(<AssistantsPanel />);
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/assistants/helper/chat/thread", {
      replace: true,
    }),
  );
  expect(api.openConversation).not.toHaveBeenCalled();
});

test("the canonical conversation uses the existing chat component inside the workspace", async () => {
  route.assistantId = "helper";
  route.sessionId = "thread";
  render(<AssistantsPanel />);
  expect(await screen.findByText("Real chat workspace")).toBeVisible();
  expect(api.forConversation).not.toHaveBeenCalled();
});

test("a task conversation waits for assistant ownership before rendering", async () => {
  route.assistantId = "helper";
  route.sessionId = "task-thread";
  let resolve!: (value: typeof helper) => void;
  api.forConversation.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  render(<AssistantsPanel />);
  await waitFor(() =>
    expect(api.forConversation).toHaveBeenCalledWith("task-thread"),
  );
  expect(screen.queryByText("Real chat workspace")).toBeNull();
  resolve(helper);
  expect(await screen.findByText("Real chat workspace")).toBeVisible();
});

test("task results retain assistant identity without a second conversation mode", async () => {
  route.assistantId = "helper";
  route.sessionId = "task-thread";
  api.forConversation.mockResolvedValue({ ...helper, context_kind: "task" });
  render(<AssistantsPanel />);
  await screen.findByText("Real chat workspace");
  expect(screen.queryByText("assistants.taskConversation")).toBeNull();
  expect(
    screen.queryByRole("button", { name: "assistants.chatWith" }),
  ).toBeNull();
  expect(
    screen.getByRole("heading", { level: 2, name: helper.name }),
  ).toHaveClass("sr-only");
});

test("role identity stays in the sidebar without duplication in the workspace header", async () => {
  const assistant = { ...helper, persona_preset_id: "role-1" };
  route.assistantId = helper.id;
  route.view = "tasks";
  api.get.mockResolvedValue(assistant);
  api.list.mockResolvedValue({ assistants: [assistant], total: 1 });
  render(<AssistantsPanel />);
  await waitFor(() => expect(profiles.persona).toHaveBeenCalledWith("role-1"));
  await waitFor(() =>
    expect(
      screen
        .getAllByTestId("assistant-avatar")
        .every((avatar) => avatar.dataset.avatar === "/role.png"),
    ).toBe(true),
  );
  expect(screen.getAllByText("Research role")).toHaveLength(1);
  const header = document.querySelector(".assistant-workspace-header")!;
  expect(
    within(header as HTMLElement).queryByTestId("assistant-avatar"),
  ).toBeNull();
  expect(screen.getAllByTestId("assistant-avatar")).toHaveLength(1);
});

test("team avatars take precedence over the role and failed metadata preserves navigation", async () => {
  const assistant = {
    ...helper,
    team_id: "team-1",
    persona_preset_id: "role-1",
  };
  api.list.mockResolvedValue({ assistants: [assistant], total: 1 });
  profiles.team.mockRejectedValue(new Error("unavailable"));
  render(<AssistantsPanel />);
  await waitFor(() => expect(profiles.team).toHaveBeenCalledWith("team-1"));
  expect(profiles.persona).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: /Researcher/ }));
  expect(navigate).toHaveBeenCalledWith("/assistants/helper");
  expect(screen.getByTestId("assistant-avatar")).toHaveAttribute(
    "data-seed",
    "Researcher",
  );
});

test("role and team metadata are not requested without read permissions", async () => {
  profiles.allowed = false;
  api.list.mockResolvedValue({
    assistants: [
      { ...helper, persona_preset_id: "role-1" },
      { ...helper, id: "team-helper", team_id: "team-1" },
    ],
    total: 2,
  });
  render(<AssistantsPanel />);
  await screen.findAllByRole("button", { name: /Researcher/ });
  expect(profiles.persona).not.toHaveBeenCalled();
  expect(profiles.team).not.toHaveBeenCalled();
});

test("a configured team uses its saved avatar", async () => {
  api.list.mockResolvedValue({
    assistants: [{ ...helper, team_id: "team-1" }],
    total: 1,
  });
  render(<AssistantsPanel />);
  await waitFor(() =>
    expect(screen.getByTestId("assistant-avatar")).toHaveAttribute(
      "data-avatar",
      "/team.png",
    ),
  );
  expect(screen.getByTestId("assistant-avatar")).toHaveAttribute(
    "data-seed",
    "team-1",
  );
});

test("permission revocation removes resolved role metadata immediately", async () => {
  api.list.mockResolvedValue({
    assistants: [{ ...helper, persona_preset_id: "role-1" }],
    total: 1,
  });
  const view = render(<AssistantsPanel />);
  await screen.findByText("Research role");
  profiles.allowed = false;
  view.rerender(<AssistantsPanel />);
  expect(screen.queryByText("Research role")).toBeNull();
  expect(screen.getByTestId("assistant-avatar")).not.toHaveAttribute(
    "data-avatar",
  );
});

test("secondary destinations have one entry in the workspace menu", async () => {
  route.assistantId = "helper";
  route.view = "tasks";
  render(<AssistantsPanel />);
  await screen.findByRole("button", { name: "common.moreOptions" });
  expect(
    screen.queryByRole("button", { name: "assistants.discussions" }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "assistants.memory" }),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.moreOptions" }));
  fireEvent.click(
    await screen.findByRole("menuitem", { name: "assistants.discussions" }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/helper/discussions");
});

test("verified work shows status beside the real chat without requiring acceptance", async () => {
  route.assistantId = "helper";
  route.sessionId = "task-thread";
  api.forConversation.mockResolvedValue({
    ...helper,
    context_kind: "task",
    context_task_id: "task-1",
  });
  api.task.mockResolvedValue({
    id: "task-1",
    session_id: "task-thread",
    description: "Report",
    state: "completed",
    run_id: "run-1",
  });
  render(<AssistantsPanel />);
  expect(
    await screen.findByText("assistants.taskStates.completed"),
  ).toBeVisible();
  expect(screen.getByText("Real chat workspace")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
});

test("Chief opens its actual persistent identity", async () => {
  api.chief.mockResolvedValue({ ...helper, id: "chief", kind: "chief" });
  render(<AssistantsPanel />);
  fireEvent.click(screen.getByRole("button", { name: /^Chief/ }));
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/assistants/chief"),
  );
});

test("background records open over the current chat and close without navigating away", async () => {
  route.assistantId = "helper";
  route.view = "chat";
  route.sessionId = "thread";
  render(<AssistantsPanel />);
  await screen.findByText("Real chat workspace");
  fireEvent.click(screen.getByRole("button", { name: "common.moreOptions" }));
  fireEvent.click(
    await screen.findByRole("menuitem", { name: "assistants.workRecords" }),
  );
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getAllByText("assistants.taskHint").length,
  ).toBeGreaterThan(0);
  expect(navigate).not.toHaveBeenCalled();
  fireEvent.keyDown(dialog, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByText("Real chat workspace")).toBeTruthy();
});

test("the workspace starts with a Chief conversation rather than a configuration form", async () => {
  api.chief.mockResolvedValue({ ...helper, id: "chief", kind: "chief" });
  render(<AssistantsPanel />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.startWithChief" }),
  );
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/assistants/chief"),
  );
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("an individual companion uses a role label rather than the workspace brand", async () => {
  render(<AssistantsPanel />);
  const companion = await screen.findByRole("button", { name: /Researcher/ });
  expect(companion).toHaveTextContent("assistants.channelBinding");
  expect(companion).not.toHaveTextContent("assistants.title");
});

test("an auxiliary page returns directly to its companion conversation", async () => {
  route.assistantId = "helper";
  route.view = "tasks";
  render(<AssistantsPanel />);
  await screen.findByRole("button", { name: "assistants.newTask" });
  fireEvent.click(
    within(screen.getByRole("banner")).getByRole("button", {
      name: "assistants.backToChat",
    }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/helper");
});
