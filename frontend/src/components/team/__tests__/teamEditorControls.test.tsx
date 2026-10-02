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
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import type { Team } from "../../../types/team";
import { TeamBuilder, type TeamBuilderHandle } from "../TeamBuilder";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  create: vi.fn(),
  upload: vi.fn(),
  compress: vi.fn(),
}));
vi.mock("../../../services/api/team", () => ({
  teamApi: { get: api.get, update: api.update, create: api.create },
}));
vi.mock("../../../services/api/personaPreset", () => ({
  personaPresetApi: {
    list: vi.fn().mockResolvedValue({ presets: [], total: 0 }),
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
  default: { success: vi.fn(), error: vi.fn() },
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
  api.get
    .mockReset()
    .mockImplementation(async (id: string) => ({
      ...team,
      id,
      avatar: id === "next" ? "/next.png" : team.avatar,
    }));
  api.update.mockReset().mockResolvedValue(team);
  api.create.mockReset().mockResolvedValue(team);
  api.compress.mockReset().mockImplementation(async (file: File) => file);
  api.upload
    .mockReset()
    .mockReturnValue({
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
