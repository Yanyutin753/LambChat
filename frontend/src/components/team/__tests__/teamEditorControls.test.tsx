/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createRef } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import type { Team } from "../../../types/team";
import type { PersonaPreset } from "../../../types";
import { TeamBuilder, type TeamBuilderHandle } from "../TeamBuilder";
import { TeamBuilderWrapper } from "../TeamBuilderWrapper";
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  create: vi.fn(),
  upload: vi.fn(),
  compress: vi.fn(),
  clone: vi.fn(),
  delete: vi.fn(),
  list: vi.fn(),
  toast: vi.fn(),
  listPresets: vi.fn(),
}));
vi.mock("../../../services/api/team", () => ({
  teamApi: {
    get: api.get,
    update: api.update,
    create: api.create,
    list: api.list,
    clone: api.clone,
    delete: api.delete,
  },
}));
vi.mock("../../../services/api/personaPreset", () => ({
  personaPresetApi: {
    list: api.listPresets,
  },
}));
vi.mock("../../../services/api/model", () => ({
  modelApi: { listAvailable: vi.fn().mockResolvedValue({ models: [] }) },
}));
vi.mock("../../../services/api/agent", () => ({
  agentApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("../../../services/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../services/api")>()),
  uploadApi: { uploadFile: api.upload },
}));
vi.mock("../../../utils/imageCompression", () => ({
  compressImageFile: api.compress,
}));
vi.mock("react-hot-toast", () => ({
  default: { success: api.toast, error: api.toast },
}));
const team: Team = {
  id: "original",
  owner_user_id: "user",
  name: "Research",
  description: "Draft",
  avatar: "/initial.png",
  tags: [],
  members: [],
  team_instructions: "",
  visibility: "private",
  created_at: "",
  updated_at: "",
};
const file = new File(["image"], "avatar.png", { type: "image/png" });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function chooseFile(container: HTMLElement) {
  fireEvent.change(container.querySelector('input[type="file"]')!, {
    target: { files: [file] },
  });
}
function editor(teamId: string | null = team.id) {
  const ref = createRef<TeamBuilderHandle>();
  const onFormStateChange = vi.fn();
  const view = render(
    <TeamBuilder
      ref={ref}
      teamId={teamId}
      onFormStateChange={onFormStateChange}
    />,
  );
  return { ...view, ref, onFormStateChange };
}
beforeEach(() => {
  resetRightPanelCoordinator();
  api.listPresets.mockReset().mockResolvedValue({ presets: [], total: 0 });
  api.get.mockReset().mockImplementation(async (id: string) => ({
    ...team,
    id,
    avatar: id === "next" ? "/next.png" : team.avatar,
  }));
  api.clone.mockReset().mockResolvedValue({ ...team, id: "cloned" });
  api.delete.mockReset().mockResolvedValue(undefined);
  api.list.mockReset().mockResolvedValue({ teams: [team], total: 1 });
  api.toast.mockReset();
  api.update.mockReset().mockResolvedValue(team);
  api.create.mockReset().mockResolvedValue(team);
  api.compress.mockReset().mockImplementation(async (file: File) => file);
  api.upload.mockReset().mockReturnValue({
    promise: Promise.resolve({ url: "/uploaded.png" }),
    abort: vi.fn(),
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("team profile and starter prompt controls have keyboard names", async () => {
  editor(null);
  expect(
    screen.getByRole("button", { name: i18n.t("personaPresets.uploadAvatar") }),
  ).toBeTruthy();
  expect(
    screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
  ).toBeRequired();
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("personaPresets.addStarterPrompt"),
    }),
  );
  expect(
    screen.getByRole("textbox", {
      name: `${i18n.t("personaPresets.starterPrompts")} 1`,
    }),
  ).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("personaPresets.pickIcon") }),
  );
  const choices = screen.getByRole("group", {
    name: i18n.t("personaPresets.pickIcon"),
  });
  expect(choices.querySelector("button")).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(
    screen.getByRole("button", { name: i18n.t("personaPresets.pickIcon") }),
  ).toHaveFocus();
});

test("an avatar image failure preserves the stored team avatar", async () => {
  const view = editor();
  await waitFor(() =>
    expect(
      view.container.querySelector('img[src*="initial.png"]'),
    ).toBeTruthy(),
  );
  fireEvent.error(view.container.querySelector('img[src*="initial.png"]')!);
  await act(async () => view.ref.current?.handleSave());
  expect(api.update).toHaveBeenCalledWith(
    team.id,
    expect.objectContaining({ avatar: team.avatar }),
  );
});

test("pending avatar upload blocks save and cannot overwrite another team", async () => {
  const request = deferred<{ url: string }>(),
    abort = vi.fn();
  api.upload.mockReturnValueOnce({ promise: request.promise, abort });
  const view = editor();
  await waitFor(() =>
    expect(
      view.container.querySelector('img[src*="initial.png"]'),
    ).toBeTruthy(),
  );
  chooseFile(view.container);
  await act(async () => view.ref.current?.handleSave());
  expect(api.update).not.toHaveBeenCalled();
  await waitFor(() => expect(api.upload).toHaveBeenCalledOnce());
  expect(view.onFormStateChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ uploadingAvatar: true }),
  );
  view.rerender(
    <TeamBuilder
      ref={view.ref}
      teamId="next"
      onFormStateChange={view.onFormStateChange}
    />,
  );
  await waitFor(() => expect(abort).toHaveBeenCalledOnce());
  await act(async () => request.resolve({ url: "/late.png" }));
  await act(async () => view.ref.current?.handleSave());
  expect(api.update).toHaveBeenCalledWith(
    "next",
    expect.objectContaining({ avatar: "/next.png" }),
  );
});

test("failed team avatar upload retains the draft and retries the same file", async () => {
  api.upload.mockImplementationOnce(() => ({
    promise: Promise.reject(new Error("offline")),
    abort: vi.fn(),
  }));
  const view = editor();
  await waitFor(() =>
    expect(
      view.container.querySelector('img[src*="initial.png"]'),
    ).toBeTruthy(),
  );
  chooseFile(view.container);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("personaPresets.avatarUploadFailed"),
  );
  expect(view.container.querySelector('img[src*="initial.png"]')).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(2));
  expect(api.upload.mock.calls[1][0]).toBe(api.upload.mock.calls[0][0]);
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  await act(async () => view.ref.current?.handleSave());
  expect(api.update).toHaveBeenCalledWith(
    team.id,
    expect.objectContaining({ avatar: "/uploaded.png" }),
  );
});

test("role search Escape closes its disclosure without reaching the parent editor", async () => {
  const escape = vi.fn();
  render(
    <div onKeyDown={escape}>
      <TeamBuilder />
    </div>,
  );
  const trigger = screen.getByRole("button", { name: i18n.t("team.addRoles") });
  fireEvent.click(trigger);
  const field = screen.getByRole("textbox", {
    name: i18n.t("team.searchRoles"),
  });
  fireEvent.keyDown(field, { key: "Escape", isComposing: true });
  expect(field).toBeInTheDocument();
  fireEvent.keyDown(field, { key: "Escape" });
  expect(
    screen.queryByRole("textbox", { name: i18n.t("team.searchRoles") }),
  ).toBeNull();
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(escape).not.toHaveBeenCalled();
});

test("existing team fields and saving wait for the requested detail", async () => {
  const request = deferred<Team>();
  api.get.mockReturnValueOnce(request.promise);
  const view = editor();
  expect(screen.getByRole("status")).toHaveTextContent(i18n.t("team.loading"));
  await act(async () => view.ref.current?.handleSave());
  expect(api.create).not.toHaveBeenCalled();
  expect(view.onFormStateChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ canSave: false }),
  );
  await act(async () => request.resolve(team));
  expect(
    screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
  ).toHaveValue(team.name);
  expect(screen.queryByRole("status")).toBeNull();
});

test("team detail failure offers retry without turning the record into a creation", async () => {
  api.get.mockRejectedValueOnce(new Error("offline"));
  const view = editor();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
  expect(view.container.querySelector("form")).toHaveAttribute(
    "aria-busy",
    "false",
  );
  await act(async () => view.ref.current?.handleSave());
  expect(api.create).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  await waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
    ).toHaveValue(team.name),
  );
  await act(async () => view.ref.current?.handleSave());
  expect(api.update).toHaveBeenCalledWith(team.id, expect.anything());
});

test.each([null, "next"])(
  "a delayed detail cannot overwrite the next editor (%s)",
  async (nextId) => {
    const old = deferred<Team>();
    api.get.mockReturnValueOnce(old.promise);
    const view = editor();
    view.rerender(
      <TeamBuilder
        ref={view.ref}
        teamId={nextId}
        onFormStateChange={view.onFormStateChange}
      />,
    );
    const name = await screen.findByRole("textbox", {
      name: i18n.t("team.teamName"),
    });
    await waitFor(() => expect(name).toBeEnabled());
    fireEvent.change(name, { target: { value: "Next draft" } });
    await act(async () => old.resolve(team));
    expect(name).toHaveValue("Next draft");
    await act(async () => view.ref.current?.handleSave());
    if (nextId)
      expect(api.update).toHaveBeenCalledWith(
        nextId,
        expect.objectContaining({ name: "Next draft" }),
      );
    else
      expect(api.create).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Next draft" }),
      );
  },
);

test("saving freezes the submitted draft, owns focus and rejects synchronous double submission", async () => {
  const request = deferred<Team>();
  api.update.mockReturnValueOnce(request.promise);
  const view = editor();
  await waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
    ).toHaveValue(team.name),
  );
  await act(async () => {
    view.ref.current?.handleSave();
    view.ref.current?.handleSave();
  });
  expect(api.update).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
  ).toBeDisabled();
  expect(document.activeElement).toBe(view.container.querySelector("form"));
  expect(view.onFormStateChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ saving: true, canSave: false }),
  );
  await act(async () => request.resolve(team));
});

test("save failure keeps fields, reports a persistent footer error and allows retry", async () => {
  api.update.mockRejectedValueOnce(new Error("offline"));
  const view = editor();
  await waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
    ).toHaveValue(team.name),
  );
  fireEvent.change(
    screen.getByRole("textbox", { name: i18n.t("team.description") }),
    { target: { value: "Keep this draft" } },
  );
  await act(async () => view.ref.current?.handleSave());
  expect(view.onFormStateChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ saveError: true, canSave: true }),
  );
  expect(
    screen.getByRole("textbox", { name: i18n.t("team.description") }),
  ).toHaveValue("Keep this draft");
  await act(async () => view.ref.current?.handleSave());
  expect(api.update).toHaveBeenLastCalledWith(
    team.id,
    expect.objectContaining({ description: "Keep this draft" }),
  );
  expect(view.onFormStateChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ saveError: false }),
  );
});

test.each([false, true])(
  "a stale save cannot close or unfreeze the next team's pending save (reject=%s)",
  async (reject) => {
    let fail!: (error: Error) => void;
    let finish!: (team: Team) => void;
    const old = new Promise<Team>((resolve, reject) => {
      finish = resolve;
      fail = reject;
    });
    const next = deferred<Team>(),
      onSave = vi.fn(),
      report = vi.fn();
    api.update.mockReturnValueOnce(old).mockReturnValueOnce(next.promise);
    const ref = createRef<TeamBuilderHandle>();
    const view = render(
      <TeamBuilder
        ref={ref}
        teamId={team.id}
        onSave={onSave}
        onFormStateChange={report}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
      ).toHaveValue(team.name),
    );
    await act(async () => {
      ref.current?.handleSave();
    });
    view.rerender(
      <TeamBuilder
        ref={ref}
        teamId="next"
        onSave={onSave}
        onFormStateChange={report}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
      ).toBeEnabled(),
    );
    await act(async () => {
      ref.current?.handleSave();
    });
    await act(async () => {
      if (reject) fail(new Error("offline"));
      else finish(team);
    });
    expect(onSave).not.toHaveBeenCalled();
    expect(api.toast).not.toHaveBeenCalled();
    expect(report).toHaveBeenLastCalledWith(
      expect.objectContaining({ saving: true, saveError: false }),
    );
    await act(async () => next.resolve({ ...team, id: "next" }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ id: "next" }),
    );
  },
);

test("closing during save suppresses its late UI effects", async () => {
  const request = deferred<Team>(),
    onSave = vi.fn();
  api.update.mockReturnValueOnce(request.promise);
  const ref = createRef<TeamBuilderHandle>();
  const view = render(
    <TeamBuilder ref={ref} teamId={team.id} onSave={onSave} />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: i18n.t("team.teamName") }),
    ).toHaveValue(team.name),
  );
  await act(async () => {
    ref.current?.handleSave();
  });
  view.unmount();
  await act(async () => request.resolve(team));
  expect(onSave).not.toHaveBeenCalled();
  expect(api.toast).not.toHaveBeenCalled();
});

test("saving closes portalled member choices and keeps them closed after completion", async () => {
  const request = deferred<Team>();
  api.update.mockReturnValueOnce(request.promise);
  api.get.mockResolvedValueOnce({
    ...team,
    members: [
      {
        member_id: "one",
        persona_preset_id: "persona",
        role_name: "Researcher",
        role_tags: [],
        role_instructions: "Keep guidance",
        position: 0,
        enabled: true,
      },
    ],
  });
  const view = editor();
  fireEvent.click(
    await screen.findByRole("button", {
      name: `${i18n.t("common.expand")} Researcher`,
    }),
  );
  const trigger = await screen.findByRole("button", {
    name: `${i18n.t("team.memberModel")} Researcher`,
  });
  fireEvent.click(trigger);
  expect(screen.getByRole("listbox")).toBeTruthy();
  await act(async () => {
    view.ref.current?.handleSave();
  });
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(trigger).toBeDisabled();
  await act(async () => request.resolve(team));
  expect(screen.queryByRole("listbox")).toBeNull();
});

test("the actual team editor footer preserves a failed draft and retries it", async () => {
  api.create.mockRejectedValueOnce(new Error("offline"));
  render(
    <MemoryRouter>
      <TeamBuilderWrapper />
    </MemoryRouter>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: i18n.t("team.newTeam") }),
  );
  const name = await screen.findByRole("textbox", {
    name: i18n.t("team.teamName"),
  });
  fireEvent.change(name, { target: { value: "Keep my team" } });
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("team.save"), exact: true }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("team.saveFailed"),
  );
  expect(name).toHaveValue("Keep my team");
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.retry"), exact: true }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("textbox", { name: i18n.t("team.teamName") }),
    ).toBeNull(),
  );
  expect(api.create).toHaveBeenLastCalledWith(
    expect.objectContaining({ name: "Keep my team" }),
  );
});

test("a delayed clone cannot overwrite another team's draft", async () => {
  const request = deferred<Team>();
  api.clone.mockReturnValueOnce(request.promise);
  const view = editor();
  await screen.findByRole("textbox", { name: i18n.t("team.teamName") });
  await act(async () => {
    view.ref.current?.handleClone();
  });
  view.rerender(<TeamBuilder ref={view.ref} teamId="next" />);
  const name = await screen.findByRole("textbox", {
    name: i18n.t("team.teamName"),
  });
  fireEvent.change(name, { target: { value: "Next draft" } });
  await act(async () =>
    request.resolve({ ...team, id: "cloned", name: "Old clone" }),
  );
  expect(name).toHaveValue("Next draft");
  expect(api.toast).not.toHaveBeenCalled();
});

test("a delayed deletion cannot close another team's editor", async () => {
  const request = deferred<void>(),
    onClose = vi.fn();
  api.delete.mockReturnValueOnce(request.promise);
  const ref = createRef<TeamBuilderHandle>();
  const view = render(
    <TeamBuilder ref={ref} teamId={team.id} onClose={onClose} />,
  );
  await screen.findByRole("textbox", { name: i18n.t("team.teamName") });
  act(() => ref.current?.handleDelete());
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.delete"), exact: true }),
  );
  view.rerender(<TeamBuilder ref={ref} teamId="next" onClose={onClose} />);
  await screen.findByRole("textbox", { name: i18n.t("team.teamName") });
  await act(async () => request.resolve());
  expect(onClose).not.toHaveBeenCalled();
  expect(api.toast).not.toHaveBeenCalled();
});

test("cloning resets errors and avatar retries belonging to the previous draft", async () => {
  api.update.mockRejectedValueOnce(new Error("offline"));
  api.upload.mockImplementationOnce(() => ({
    promise: Promise.reject(new Error("offline")),
    abort: vi.fn(),
  }));
  const view = editor();
  await screen.findByRole("textbox", { name: i18n.t("team.teamName") });
  await act(async () => view.ref.current?.handleSave());
  chooseFile(view.container);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("personaPresets.avatarUploadFailed"),
  );
  await act(async () => view.ref.current?.handleClone());
  expect(view.onFormStateChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ saveError: false }),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    screen.queryByRole("button", { name: i18n.t("common.retry"), exact: true }),
  ).toBeNull();
});

const catalogRole = {
  id: "role-1",
  name: "Catalog researcher",
  description: "Research guidance",
  tags: [],
  avatar: null,
} as PersonaPreset;

test("role catalog failures are retriable and keep the team's draft", async () => {
  api.listPresets
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ presets: [catalogRole], total: 1 });
  const view = editor(null);
  const name = screen.getByRole("textbox", { name: i18n.t("team.teamName") });
  fireEvent.change(name, { target: { value: "Keep my draft" } });
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("team.addRoles"), exact: true }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
  expect(screen.queryByText(i18n.t("team.noRolesFound"))).toBeNull();
  screen
    .getByRole("button", { name: i18n.t("common.retry"), exact: true })
    .focus();
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.retry"), exact: true }),
  );
  expect(
    screen.getByRole("textbox", { name: i18n.t("team.searchRoles") }),
  ).toHaveFocus();
  fireEvent.click(
    await screen.findByRole("button", { name: /Catalog researcher/ }),
  );
  expect(name).toHaveValue("Keep my draft");
  await act(async () => view.ref.current?.handleSave());
  expect(api.create).toHaveBeenCalledWith(
    expect.objectContaining({
      name: "Keep my draft",
      members: [expect.objectContaining({ persona_preset_id: catalogRole.id })],
    }),
  );
});

test("role catalog waits visibly and never offers stale choices while loading", async () => {
  const request = deferred<{ presets: PersonaPreset[]; total: number }>();
  api.listPresets.mockReturnValueOnce(request.promise);
  editor(null);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("team.addRoles"), exact: true }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    i18n.t("team.loadingRoles"),
  );
  expect(screen.queryByText(i18n.t("team.noRolesFound"))).toBeNull();
  await act(async () => request.resolve({ presets: [catalogRole], total: 1 }));
  expect(
    await screen.findByRole("button", { name: /Catalog researcher/ }),
  ).toBeEnabled();
});

test("role catalog paginates on the server and searches beyond the first page", async () => {
  api.listPresets.mockImplementation(async ({ skip, q }) => ({
    presets: [
      {
        ...catalogRole,
        id: `${skip}`,
        name: q ? "Role beyond 100" : `Role ${skip}`,
      },
    ],
    total: q ? 1 : 125,
  }));
  editor(null);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("team.addRoles"), exact: true }),
  );
  await screen.findByRole("button", { name: /Role 0/ });
  expect(api.listPresets).toHaveBeenLastCalledWith(
    expect.objectContaining({ skip: 0, limit: 20 }),
  );
  screen
    .getByRole("button", { name: i18n.t("common.next"), exact: true })
    .focus();
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.next"), exact: true }),
  );
  expect(
    screen.getByRole("textbox", { name: i18n.t("team.searchRoles") }),
  ).toHaveFocus();
  await screen.findByRole("button", { name: /Role 20/ });
  fireEvent.change(
    screen.getByRole("textbox", { name: i18n.t("team.searchRoles") }),
    { target: { value: "Beyond" } },
  );
  await screen.findByRole("button", { name: /Role beyond 100/ });
  expect(api.listPresets).toHaveBeenLastCalledWith({
    skip: 0,
    limit: 20,
    q: "Beyond",
  });
});

test("a delayed catalog response cannot replace the current search results", async () => {
  const old = deferred<{ presets: PersonaPreset[]; total: number }>();
  api.listPresets.mockReturnValueOnce(old.promise).mockResolvedValue({
    presets: [{ ...catalogRole, name: "Current result" }],
    total: 1,
  });
  editor(null);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("team.addRoles"), exact: true }),
  );
  await waitFor(() => expect(api.listPresets).toHaveBeenCalledOnce());
  fireEvent.change(
    screen.getByRole("textbox", { name: i18n.t("team.searchRoles") }),
    { target: { value: "Current" } },
  );
  await screen.findByRole("button", { name: /Current result/ });
  await act(async () => old.resolve({ presets: [catalogRole], total: 1 }));
  expect(screen.getByRole("button", { name: /Current result/ })).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: /Catalog researcher/ }),
  ).toBeNull();
});
