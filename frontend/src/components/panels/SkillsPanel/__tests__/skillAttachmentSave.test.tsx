/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useSkills } from "../../../../hooks/useSkills";
import { skillApi } from "../../../../services/api/skill";
import { SkillForm } from "../../../skill/SkillForm";
import { useSkillsActions } from "../useSkillsActions";

vi.mock("../../../../hooks/useSkills", () => ({ useSkills: vi.fn() }));
vi.mock("../../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
const create = vi.fn();
const update = vi.fn();
const getSkill = vi.fn();
const refresh = vi.fn();
beforeEach(() => {
  vi.mocked(useSkills).mockReturnValue({
    skills: [],
    availableTags: [],
    total: 0,
    isLoading: false,
    error: null,
    createSkill: create,
    updateSkill: update,
    getSkill,
    fetchSkills: refresh,
  } as unknown as ReturnType<typeof useSkills>);
  create.mockResolvedValue(true);
  update.mockResolvedValue(true);
  getSkill.mockResolvedValue({
    name: "research",
    files: {},
    filePaths: ["SKILL.md", "assets/a.png"],
  });
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:preview");
      static revokeObjectURL = vi.fn();
    },
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function Editor() {
  const a = useSkillsActions();
  return (
    <>
      <button onClick={a.handleCreate}>New skill</button>
      <button onClick={a.handleCancel}>Close editor</button>
      <button
        onClick={() =>
          a.handleEdit({ name: "other" } as Parameters<typeof a.handleEdit>[0])
        }
      >
        Edit another skill
      </button>
      {a.showModal && (
        <SkillForm
          skill={a.editingSkill}
          onSave={a.handleSave}
          onCancel={a.handleCancel}
          onComplete={a.handleComplete}
          isNameLocked={a.isNameLocked}
        />
      )}
    </>
  );
}
function open() {
  render(
    <MemoryRouter>
      <Editor />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "New skill" }));
  fireEvent.change(screen.getByRole("textbox", { name: "skills.form.name" }), {
    target: { value: "research" },
  });
  fireEvent.change(
    screen.getByRole("textbox", { name: "skills.form.description" }),
    { target: { value: "Keep this draft" } },
  );
  const a = new File(["image A"], "a.png", { type: "image/png" });
  const b = new File(["image B"], "b.png", { type: "image/png" });
  fireEvent.change(document.querySelector('input[type="file"]')!, {
    target: { files: [a, b] },
  });
  return { a, b };
}

test("attachment failure keeps the form and retries only the unfinished file as an update", async () => {
  let finish!: () => void;
  const uploaded = vi
    .spyOn(skillApi, "uploadBinaryFile")
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () =>
            resolve({
              message: "Saved",
              url: "/a.png",
              mime_type: "image/png",
              size: 7,
            });
        }),
    )
    .mockRejectedValueOnce(new Error("Unavailable"))
    .mockResolvedValue({
      message: "Saved",
      url: "/b.png",
      mime_type: "image/png",
      size: 7,
    });
  const { a, b } = open();
  fireEvent.click(
    screen.getByRole("button", { name: "skills.form.createSkill" }),
  );
  await waitFor(() =>
    expect(uploaded).toHaveBeenCalledWith("research", "assets/a.png", a),
  );
  expect(
    screen.getByRole("textbox", { name: "skills.form.description" }),
  ).toHaveValue("Keep this draft");
  expect(screen.getByRole("button", { name: "common.cancel" })).toBeDisabled();
  expect(document.activeElement).toBe(document.querySelector("form"));
  await act(async () => finish());
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "skills.uploadFailed",
  );
  expect(
    screen.getByRole("textbox", { name: "skills.form.name" }),
  ).toBeDisabled();
  const retry = screen.getByRole("button", { name: "common.retry" });
  expect(retry).toBeEnabled();
  await act(async () => fireEvent.click(retry));
  expect(create).toHaveBeenCalledTimes(1);
  expect(refresh).toHaveBeenCalledTimes(1);
  expect(update).toHaveBeenCalledTimes(1);
  expect(uploaded.mock.calls.map((call) => call[1])).toEqual([
    "assets/a.png",
    "assets/b.png",
    "assets/b.png",
  ]);
  expect(uploaded).toHaveBeenLastCalledWith("research", "assets/b.png", b);
  expect(
    screen.queryByRole("textbox", { name: "skills.form.description" }),
  ).toBeNull();
});

test("choosing a duplicate attachment preserves the first file and blocks path renaming", async () => {
  open();
  const input = screen.getByRole("textbox", { name: "skills.form.filePath" });
  expect(input).toBeDisabled();
  fireEvent.change(document.querySelector('input[type="file"]')!, {
    target: {
      files: [new File(["replacement"], "b.png", { type: "image/png" })],
    },
  });
  expect(
    screen.getByText("skills.form.validation.duplicateFilePaths"),
  ).toBeInTheDocument();
  expect(
    screen.getAllByRole("button", { name: "assets/b.png", exact: true }),
  ).toHaveLength(1);
  const uploaded = vi.spyOn(skillApi, "uploadBinaryFile").mockResolvedValue({
    message: "Saved",
    url: "/image.png",
    mime_type: "image/png",
    size: 7,
  });
  await act(async () =>
    fireEvent.click(
      screen.getByRole("button", { name: "skills.form.createSkill" }),
    ),
  );
  expect(uploaded.mock.calls[1][2].size).toBe(7);
});

test("removing a failed attachment retries without deleting a file that never existed", async () => {
  vi.spyOn(skillApi, "uploadBinaryFile")
    .mockResolvedValueOnce({
      message: "Saved",
      url: "/a.png",
      mime_type: "image/png",
      size: 7,
    })
    .mockRejectedValueOnce(new Error("Unavailable"));
  open();
  await act(async () =>
    fireEvent.click(
      screen.getByRole("button", { name: "skills.form.createSkill" }),
    ),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "common.remove: assets/b.png" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "common.remove: assets/a.png" }),
  );
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "common.retry" })),
  );
  expect(update.mock.calls[0][1].deletedFiles).toEqual(["assets/a.png"]);
});

test("a closed editor save cannot lock the next draft name", async () => {
  let finish!: (value: boolean) => void;
  create.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  open();
  fireEvent.click(
    screen.getByRole("button", { name: "skills.form.createSkill" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Close editor" }));
  fireEvent.click(screen.getByRole("button", { name: "New skill" }));
  await act(async () => finish(true));
  expect(
    screen.getByRole("textbox", { name: "skills.form.name" }),
  ).toBeEnabled();
  expect(
    screen.getByRole("textbox", { name: "skills.form.description" }),
  ).toHaveValue("");
});

test("an old upload cannot close an edit request for another skill", async () => {
  let finishUpload!: () => void;
  let finishDetail!: (value: unknown) => void;
  vi.spyOn(skillApi, "uploadBinaryFile")
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishUpload = () =>
            resolve({
              message: "Saved",
              url: "/a.png",
              mime_type: "image/png",
              size: 7,
            });
        }),
    )
    .mockResolvedValue({
      message: "Saved",
      url: "/b.png",
      mime_type: "image/png",
      size: 7,
    });
  getSkill.mockReturnValueOnce(
    new Promise((resolve) => {
      finishDetail = resolve;
    }),
  );
  open();
  fireEvent.click(
    screen.getByRole("button", { name: "skills.form.createSkill" }),
  );
  await waitFor(() => expect(finishUpload).toBeTypeOf("function"));
  fireEvent.click(screen.getByRole("button", { name: "Edit another skill" }));
  expect(
    screen.queryByRole("textbox", { name: "skills.form.name" }),
  ).toBeNull();
  await act(async () => finishUpload());
  await act(async () =>
    finishDetail({
      name: "other",
      description: "Other draft",
      files: { "SKILL.md": "# Other" },
      tags: [],
      enabled: true,
    }),
  );
  expect(screen.getByRole("textbox", { name: "skills.form.name" })).toHaveValue(
    "other",
  );
});
