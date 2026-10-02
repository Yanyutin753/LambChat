/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SkillForm } from "../SkillForm";
import { skillApi } from "../../../services/api/skill";
import type {
  SkillResponse,
  SkillFileResponse,
  SkillCreate,
} from "../../../types/skill";

vi.mock("../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const skill: SkillResponse = {
  name: "research",
  description: "Research workflow",
  tags: [],
  enabled: true,
  source: "manual",
  installed_from: "manual",
  files: {},
  filePaths: ["SKILL.md", "a.md", "b.md"],
  file_count: 3,
  is_published: false,
  marketplace_is_active: true,
};
function deferred() {
  let resolve!: (value: SkillFileResponse) => void;
  const promise = new Promise<SkillFileResponse>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test.each([false, true])(
  "failed file offers retry and retains metadata (fullscreen=%s)",
  async (fullscreen) => {
    vi.spyOn(skillApi, "getFile")
      .mockRejectedValueOnce(new Error("Unavailable"))
      .mockResolvedValue({ content: "# Recovered instructions" });
    render(
      <SkillForm
        skill={skill}
        onSave={async () => false}
        onCancel={() => {}}
      />,
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "skills.form.description" }),
      { target: { value: "Keep this draft" } },
    );
    if (fullscreen)
      fireEvent.click(
        screen.getByRole("button", { name: "skills.form.fullscreenEditor" }),
      );
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "SKILL.md" })).toBeNull();
    const retry = screen.getByRole("button", { name: "common.retry" });
    retry.focus();
    const form = retry.closest("form");
    fireEvent.click(retry);
    const editor = await screen.findByRole("textbox", { name: "SKILL.md" });
    expect(editor.textContent).toContain("Recovered instructions");
    expect(document.activeElement).toBe(form);
    if (fullscreen)
      fireEvent.click(
        screen.getByRole("button", { name: "skills.form.exitFullscreen" }),
      );
    expect(
      (
        screen.getByRole("textbox", {
          name: "skills.form.description",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("Keep this draft");
  },
);

test("a file response stays with its path after another file is removed", async () => {
  const pending = deferred();
  vi.spyOn(skillApi, "getFile").mockImplementation(async (_name, path) =>
    path === "b.md" ? pending.promise : { content: "# Existing instructions" },
  );
  render(
    <SkillForm skill={skill} onSave={async () => false} onCancel={() => {}} />,
  );
  await screen.findByRole("textbox", { name: "SKILL.md" });
  fireEvent.click(screen.getByRole("button", { name: "b.md", exact: true }));
  fireEvent.click(screen.getByRole("button", { name: "common.remove: a.md" }));
  await act(async () => {
    pending.resolve({ content: "B belongs to b.md" });
  });
  expect(
    (await screen.findByRole("textbox", { name: "b.md" })).textContent,
  ).toContain("B belongs to b.md");
  fireEvent.click(
    screen.getByRole("button", { name: "SKILL.md", exact: true }),
  );
  expect(
    screen.getByRole("textbox", { name: "SKILL.md" }).textContent,
  ).toContain("Existing instructions");
});

test("a previous skill response cannot replace the current skill contents", async () => {
  const pending = deferred();
  vi.spyOn(skillApi, "getFile").mockImplementation(async (name) =>
    name === "research" ? pending.promise : { content: "# Current skill" },
  );
  const view = render(
    <SkillForm skill={skill} onSave={async () => false} onCancel={() => {}} />,
  );
  view.rerender(
    <SkillForm
      skill={{ ...skill, name: "current" }}
      onSave={async () => false}
      onCancel={() => {}}
    />,
  );
  expect(
    (await screen.findByRole("textbox", { name: "SKILL.md" })).textContent,
  ).toContain("Current skill");
  await act(async () => {
    pending.resolve({ content: "# Previous skill" });
  });
  expect(
    screen.getByRole("textbox", { name: "SKILL.md" }).textContent,
  ).toContain("Current skill");
});

test("a duplicate rename preserves the original path and draft during another file request", async () => {
  const pending = deferred();
  vi.spyOn(skillApi, "getFile").mockImplementation(async (_name, path) =>
    path === "b.md" ? pending.promise : { content: "# Keep A instructions" },
  );
  render(
    <SkillForm skill={skill} onSave={async () => false} onCancel={() => {}} />,
  );
  await screen.findByRole("textbox", { name: "SKILL.md" });
  fireEvent.click(screen.getByRole("button", { name: "a.md", exact: true }));
  await screen.findByRole("textbox", { name: "a.md" });
  fireEvent.click(screen.getByRole("button", { name: "b.md", exact: true }));
  fireEvent.click(screen.getByRole("button", { name: "a.md", exact: true }));
  fireEvent.change(
    screen.getByRole("textbox", { name: "skills.form.filePath" }),
    { target: { value: "b.md" } },
  );
  expect(
    (
      screen.getByRole("textbox", {
        name: "skills.form.filePath",
      }) as HTMLInputElement
    ).value,
  ).toBe("a.md");
  expect(
    screen.getByText("skills.form.validation.duplicateFilePaths"),
  ).toBeTruthy();
  expect(
    screen
      .getByRole("textbox", { name: "skills.form.filePath" })
      .getAttribute("aria-invalid"),
  ).toBe("true");
  await act(async () => {
    pending.resolve({ content: "# Server B instructions" });
  });
  expect(screen.getByRole("textbox", { name: "a.md" }).textContent).toContain(
    "Keep A instructions",
  );
  fireEvent.click(screen.getByRole("button", { name: "b.md", exact: true }));
  expect(screen.getByRole("textbox", { name: "b.md" }).textContent).toContain(
    "Server B instructions",
  );
});

test("remaining unnamed drafts can be named and saved after another unnamed file is removed", async () => {
  vi.spyOn(skillApi, "getFile").mockResolvedValue({
    content: "# Instructions",
  });
  const saved: SkillCreate[] = [];
  render(
    <SkillForm
      skill={skill}
      onSave={async (data) => {
        saved.push(data);
        return false;
      }}
      onCancel={() => {}}
    />,
  );
  await screen.findByRole("textbox", { name: "SKILL.md" });
  fireEvent.click(screen.getByRole("button", { name: "skills.form.addFile" }));
  fireEvent.click(screen.getByRole("button", { name: "skills.form.addFile" }));
  fireEvent.click(
    screen.getAllByRole("button", {
      name: "common.remove: skills.form.untitled",
    })[0],
  );
  const path = screen.getByRole("textbox", {
    name: "skills.form.filePath",
  }) as HTMLInputElement;
  expect(path.disabled).toBe(false);
  fireEvent.change(path, { target: { value: "new.md" } });
  fireEvent.click(screen.getByRole("button", { name: "skills.form.addFile" }));
  fireEvent.change(path, { target: { value: "second.md" } });
  fireEvent.click(
    screen.getByRole("button", { name: "skills.form.saveChanges" }),
  );
  expect(saved[0]?.files?.["new.md"]).toBe("");
  expect(saved[0]?.files?.["second.md"]).toBe("");
});
