/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { usePersonaPresets } from "../../../hooks/usePersonaPresets";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { PersonaEditorModal } from "../PersonaEditorModal";
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";
import type { PersonaPreset } from "../../../types";

const api = vi.hoisted(() => ({
  compress: vi.fn(),
  upload: vi.fn(),
  toast: vi.fn(),
  update: vi.fn(),
  list: vi.fn(),
}));
vi.mock("../../../utils/imageCompression", () => ({
  compressImageFile: api.compress,
}));
vi.mock("../../../services/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../services/api")>()),
  uploadApi: { uploadFile: api.upload },
  personaPresetApi: { update: api.update, list: api.list },
}));
vi.mock("../../../services/api/mcp", () => ({
  mcpApi: { list: vi.fn().mockResolvedValue({ servers: [] }) },
}));
vi.mock("../../../services/api/skill", () => ({
  skillApi: { list: vi.fn().mockResolvedValue({ skills: [], total: 0 }) },
}));
vi.mock("react-hot-toast", () => ({
  default: { success: api.toast, error: api.toast },
}));

beforeEach(() => {
  resetRightPanelCoordinator();
  api.compress.mockReset().mockImplementation(async (file: File) => file);
  api.upload.mockReset().mockReturnValue({
    promise: Promise.resolve({ url: "/uploaded.png" }),
    abort: vi.fn(),
  });
  api.toast.mockReset();
  api.update.mockReset();
  api.list.mockReset().mockResolvedValue({ presets: [], total: 0 });
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const preset: PersonaPreset = {
  id: "original",
  name: "Original",
  description: "",
  avatar: "/initial.png",
  scope: "user",
  status: "draft",
  visibility: "private",
  version: 1,
  usage_count: 0,
  tags: [],
  system_prompt: "Keep my instructions",
  skill_names: [],
  mcp_server_names: [],
  starter_prompts: [],
  created_at: "2026-10-02",
  updated_at: "2026-10-02",
};
function props() {
  return {
    showModal: true,
    editingPreset: preset,
    editorScope: "user" as const,
    canAdmin: true,
    isMutating: false,
    createPreset: vi.fn().mockResolvedValue(preset),
    updatePreset: vi.fn().mockResolvedValue(preset),
    onClose: vi.fn(),
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
const file = new File(["image"], "avatar.png", { type: "image/png" });
function chooseFile(container: HTMLElement) {
  fireEvent.change(container.querySelector('input[type="file"]')!, {
    target: { files: [file] },
  });
}

test("pending persona save freezes the submitted draft, keeps focus and prevents double submission", async () => {
  const p = props(),
    request = deferred<PersonaPreset>();
  p.updatePreset.mockReturnValue(request.promise);
  render(<PersonaEditorModal {...p} />);
  const save = screen.getByRole("button", { name: i18n.t("common.save") });
  fireEvent.click(save);
  fireEvent.click(save);
  expect(p.updatePreset).toHaveBeenCalledTimes(1);
  expect(
    screen.getByRole("textbox", { name: i18n.t("personaPresets.name") }),
  ).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent(i18n.t("common.saving"));
  expect(document.activeElement).not.toBe(document.body);
  await act(async () => request.resolve(preset));
});

test.each([false, true])(
  "failed persona save persists beside retry and preserves its payload (throws=%s)",
  async (throws) => {
    const p = props();
    if (throws) p.updatePreset.mockRejectedValueOnce(new Error("offline"));
    else p.updatePreset.mockResolvedValueOnce(null);
    render(<PersonaEditorModal {...p} />);
    fireEvent.change(
      screen.getByRole("textbox", { name: i18n.t("personaPresets.name") }),
      { target: { value: "Edited draft" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.save") }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      i18n.t("personaPresets.updateFailed"),
    );
    expect(
      screen.getByRole("textbox", { name: i18n.t("personaPresets.name") }),
    ).toHaveValue("Edited draft");
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.retry") }),
    );
    await waitFor(() => expect(p.updatePreset).toHaveBeenCalledTimes(2));
    expect(p.updatePreset.mock.calls[1]).toEqual(p.updatePreset.mock.calls[0]);
    await waitFor(() => expect(p.onClose).toHaveBeenCalledOnce());
  },
);

test.each([false, true])(
  "late save cannot close a newer editor session (same record=%s)",
  async (same) => {
    const p = props(),
      request = deferred<PersonaPreset>();
    p.updatePreset.mockReturnValueOnce(request.promise);
    const view = render(<PersonaEditorModal {...p} />);
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.save") }),
    );
    if (same) view.rerender(<PersonaEditorModal {...p} showModal={false} />);
    view.rerender(
      <PersonaEditorModal
        {...p}
        editingPreset={same ? preset : { ...preset, id: "next", name: "Next" }}
      />,
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: i18n.t("personaPresets.name") }),
      { target: { value: "New draft" } },
    );
    await act(async () => request.resolve(preset));
    expect(p.onClose).not.toHaveBeenCalled();
    expect(
      screen.getByRole("textbox", { name: i18n.t("personaPresets.name") }),
    ).toHaveValue("New draft");
  },
);

test("a failed avatar preview never clears the saved avatar value", async () => {
  const p = props(),
    view = render(<PersonaEditorModal {...p} />);
  fireEvent.error(
    view.container.ownerDocument.querySelector('img[src*="initial.png"]')!,
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(p.updatePreset).toHaveBeenCalledWith(
      preset.id,
      expect.objectContaining({ avatar: preset.avatar }),
    ),
  );
});

test("avatar upload blocks save, aborts on record change and cannot replace the next avatar", async () => {
  const request = deferred<{ url: string }>(),
    abort = vi.fn();
  api.upload.mockReturnValueOnce({ promise: request.promise, abort });
  const p = props(),
    view = render(<PersonaEditorModal {...p} />);
  chooseFile(document.body);
  await waitFor(() => expect(api.upload).toHaveBeenCalledOnce());
  expect(
    screen.getByRole("button", { name: i18n.t("common.save") }),
  ).toBeDisabled();
  view.rerender(
    <PersonaEditorModal
      {...p}
      editingPreset={{ ...preset, id: "next", avatar: "/next.png" }}
    />,
  );
  expect(abort).toHaveBeenCalledOnce();
  await act(async () => request.resolve({ url: "/late.png" }));
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(p.updatePreset).toHaveBeenCalledWith(
      "next",
      expect.objectContaining({ avatar: "/next.png" }),
    ),
  );
});

test("closing while avatar compression waits does not start a later upload", async () => {
  const compression = deferred<File>();
  api.compress.mockReturnValueOnce(compression.promise);
  const p = props(),
    view = render(<PersonaEditorModal {...p} />);
  chooseFile(document.body);
  await waitFor(() => expect(api.compress).toHaveBeenCalledOnce());
  view.rerender(<PersonaEditorModal {...p} showModal={false} />);
  await act(async () => compression.resolve(file));
  expect(api.upload).not.toHaveBeenCalled();
  expect(api.toast).not.toHaveBeenCalled();
});

test("failed avatar upload retains the original and can retry the same file", async () => {
  api.upload.mockImplementationOnce(() => ({
    promise: Promise.reject(new Error("offline")),
    abort: vi.fn(),
  }));
  const p = props();
  render(<PersonaEditorModal {...p} />);
  chooseFile(document.body);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("personaPresets.avatarUploadFailed"),
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(2));
  expect(api.upload.mock.calls[1][0]).toBe(api.upload.mock.calls[0][0]);
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(p.updatePreset).toHaveBeenCalledWith(
      preset.id,
      expect.objectContaining({ avatar: "/uploaded.png" }),
    ),
  );
});

test("avatar and icon choice have keyboard names and Escape returns to its disclosure", async () => {
  const user = userEvent.setup(),
    p = props();
  render(<PersonaEditorModal {...p} />);
  expect(
    screen.getByRole("button", { name: i18n.t("personaPresets.changeAvatar") }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", {
      name: `${i18n.t("common.remove")} ${i18n.t("personaPresets.avatar")}`,
    }),
  ).toBeInTheDocument();
  const trigger = screen.getByRole("button", {
    name: i18n.t("personaPresets.pickIcon"),
  });
  await user.click(trigger);
  const choice = screen.getByRole("button", {
    name: i18n.t("personaPresets.emojiRobot"),
    exact: true,
  });
  choice.focus();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(p.onClose).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("button", {
      name: i18n.t("personaPresets.emojiRobot"),
      exact: true,
    }),
  ).toBeNull();
});

test("removing an avatar leaves keyboard focus on the icon choice and does not clear other fields", async () => {
  const p = props();
  render(<PersonaEditorModal {...p} />);
  fireEvent.click(
    screen.getByRole("button", {
      name: `${i18n.t("common.remove")} ${i18n.t("personaPresets.avatar")}`,
    }),
  );
  expect(
    screen.getByRole("button", { name: i18n.t("personaPresets.pickIcon") }),
  ).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(p.updatePreset).toHaveBeenCalledWith(
      preset.id,
      expect.objectContaining({
        avatar: null,
        name: preset.name,
        system_prompt: preset.system_prompt,
      }),
    ),
  );
});

test("avatar icon Escape during composition keeps its choices and parent editor open", async () => {
  const p = props();
  render(<PersonaEditorModal {...p} />);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("personaPresets.pickIcon") }),
  );
  const choice = screen.getByRole("button", {
    name: i18n.t("personaPresets.emojiRobot"),
    exact: true,
  });
  fireEvent.keyDown(choice, { key: "Escape", isComposing: true });
  expect(choice).toBeInTheDocument();
  expect(p.onClose).not.toHaveBeenCalled();
});

function SharedMutationEditor() {
  const [editing, setEditing] = useState<PersonaPreset | null>(preset);
  const { isMutating, createPreset, updatePreset } = usePersonaPresets();
  return (
    <>
      <button onClick={() => setEditing({ ...preset, id: "next" })}>
        Open next draft
      </button>
      <PersonaEditorModal
        showModal={!!editing}
        editingPreset={editing}
        editorScope="user"
        canAdmin
        isMutating={isMutating}
        createPreset={createPreset}
        updatePreset={updatePreset}
        onClose={() => setEditing(null)}
      />
    </>
  );
}

test("an earlier shared mutation and list refresh block concurrent save without freezing the next draft", async () => {
  const request = deferred<PersonaPreset>(),
    refresh = deferred<{ presets: PersonaPreset[]; total: number }>();
  api.update.mockReturnValueOnce(request.promise);
  api.list
    .mockResolvedValueOnce({ presets: [], total: 0 })
    .mockReturnValueOnce(refresh.promise);
  render(<SharedMutationEditor />);
  await waitFor(() => expect(api.list).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() => expect(api.update).toHaveBeenCalledOnce());
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.cancel") }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Open next draft" }));
  const name = screen.getByRole("textbox", {
    name: i18n.t("personaPresets.name"),
  });
  expect(name).toBeEnabled();
  fireEvent.change(name, { target: { value: "Next draft" } });
  expect(
    screen.getByRole("button", { name: i18n.t("common.save") }),
  ).toBeDisabled();
  expect(screen.queryByRole("status")).toBeNull();
  await act(async () => request.resolve(preset));
  await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
  expect(name).toBeEnabled();
  expect(name).toHaveValue("Next draft");
  expect(
    screen.getByRole("button", { name: i18n.t("common.save") }),
  ).toBeDisabled();
  await act(async () => refresh.resolve({ presets: [], total: 0 }));
  expect(name).toHaveValue("Next draft");
  expect(
    screen.getByRole("button", { name: i18n.t("common.save") }),
  ).toBeEnabled();
});
