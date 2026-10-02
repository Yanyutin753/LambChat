/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SkillForm } from "../SkillForm";
import { FileTabs } from "../FileTabs";
import { FileTreeItem } from "../FileTreeItem";

Element.prototype.scrollIntoView = vi.fn();

test("removing a tag returns focus to the tag input and preserves other tags", async () => {
  render(<SkillForm onSave={vi.fn()} onCancel={vi.fn()} />);
  const input = screen.getByRole("textbox", { name: "adminMarketplace.tags" });
  fireEvent.change(input, { target: { value: "research, mobile" } });
  screen.getByRole("button", { name: "common.remove: mobile" }).focus();
  await userEvent.keyboard(" ");
  expect((input as HTMLInputElement).value).toBe("research");
  expect(document.activeElement).toBe(input);
});

vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../SkillEditor", () => ({
  SkillEditor: ({
    value,
    onChange,
    readOnly,
    filePath,
  }: {
    value: string;
    onChange: (value: string) => void;
    readOnly?: boolean;
    filePath?: string;
  }) => (
    <textarea
      aria-label={filePath}
      value={value}
      readOnly={readOnly}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("skill metadata and file path have associated labels and validation feedback", () => {
  render(<SkillForm onSave={vi.fn()} onCancel={vi.fn()} />);
  expect(
    screen.getByRole("textbox", { name: "skills.form.name" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("textbox", { name: "skills.form.description" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("textbox", { name: "adminMarketplace.tags" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("textbox", { name: "skills.form.filePath" }),
  ).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "skills.form.createSkill" }),
  );
  const name = screen.getByRole("textbox", { name: "skills.form.name" });
  expect(name.getAttribute("aria-invalid")).toBe("true");
  expect(document.activeElement).toBe(name);
  expect(
    document.getElementById(name.getAttribute("aria-describedby")!)
      ?.textContent,
  ).toBe("skills.form.validation.nameRequired");
});

test("removing a file preserves the selected remaining file and returns keyboard focus", async () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    {},
  ] as unknown as DOMRectList);
  render(<SkillForm onSave={vi.fn()} onCancel={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "skills.form.addFile" }));
  fireEvent.change(
    screen.getByRole("textbox", { name: "skills.form.filePath" }),
    { target: { value: "first.md" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "skills.form.addFile" }));
  fireEvent.change(
    screen.getByRole("textbox", { name: "skills.form.filePath" }),
    { target: { value: "second.md" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "first.md" }));
  const remove = screen.getByRole("button", {
    name: "common.remove: SKILL.md",
  });
  remove.focus();
  await userEvent.keyboard("{Enter}");
  expect(
    (
      screen.getByRole("textbox", {
        name: "skills.form.filePath",
      }) as HTMLInputElement
    ).value,
  ).toBe("first.md");
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "first.md" }),
  );
});

test("file removal is a named native keyboard button independent of file selection", async () => {
  const remove = vi.fn(),
    select = vi.fn();
  render(
    <FileTabs
      files={[
        { path: "SKILL.md", content: "" },
        { path: "docs/help.md", content: "" },
      ]}
      activeFileIndex={0}
      onSelect={select}
      onRemove={remove}
      untitledLabel="Untitled"
    />,
  );
  const button = screen.getByRole("button", {
    name: "common.remove: docs/help.md",
  });
  expect(button.tagName).toBe("BUTTON");
  expect(button.closest("button button")).toBeNull();
  button.focus();
  await userEvent.keyboard(" ");
  expect(remove).toHaveBeenCalledWith(1);
  expect(select).not.toHaveBeenCalled();
  expect(
    screen
      .getByRole("button", { name: "SKILL.md" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
});

test("desktop file tree removal is independent and folder expansion is announced", async () => {
  const remove = vi.fn(),
    select = vi.fn();
  render(
    <FileTreeItem
      node={{
        name: "docs",
        type: "folder",
        children: [{ name: "help.md", type: "file", fileIndex: 1 }],
      }}
      depth={0}
      activeFileIndex={1}
      onSelect={select}
      onRemove={remove}
      canRemove
    />,
  );
  const folder = screen.getByRole("button", { name: "docs" });
  expect(folder.getAttribute("aria-expanded")).toBe("true");
  const button = screen.getByRole("button", { name: "common.remove: help.md" });
  button.focus();
  await userEvent.keyboard("{Enter}");
  expect(remove).toHaveBeenCalledWith(1);
  expect(select).not.toHaveBeenCalled();
});

test("fullscreen is an isolated labelled dialog and Escape retains edited text", async () => {
  const background = document.createElement("div");
  background.dataset.rightPanelRoot = "";
  document.body.append(background);
  render(<SkillForm onSave={vi.fn()} onCancel={vi.fn()} />);
  fireEvent.click(
    screen.getByRole("button", { name: "skills.form.fullscreenEditor" }),
  );
  const dialog = screen.getByRole("dialog", {
    name: "skills.form.fullscreenEditor",
  });
  expect(background.inert).toBe(true);
  expect(document.activeElement).toBe(dialog);
  fireEvent.change(within(dialog).getByRole("textbox", { name: "SKILL.md" }), {
    target: { value: "updated instructions" },
  });
  fireEvent.keyDown(document, { key: "Escape", isComposing: true });
  expect(screen.getByRole("dialog")).toBeTruthy();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(
    (screen.getByRole("textbox", { name: "SKILL.md" }) as HTMLTextAreaElement)
      .value,
  ).toBe("updated instructions");
  expect(background.inert).toBe(false);
  background.remove();
});

test("deleting another file while the selected folder is collapsed retains a visible focus target", () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(
    function (this: HTMLElement) {
      return (this.closest(".skill-file-tab")
        ? []
        : [{}]) as unknown as DOMRectList;
    },
  );
  render(<SkillForm onSave={vi.fn()} onCancel={vi.fn()} />);
  for (const path of ["docs/help.md", "zzz.md"]) {
    fireEvent.click(
      screen.getByRole("button", { name: "skills.form.addFile" }),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "skills.form.filePath" }),
      { target: { value: path } },
    );
  }
  fireEvent.click(
    screen.getByRole("button", { name: "skills.form.fullscreenEditor" }),
  );
  const sidebar = document.querySelector(".skill-file-sidebar")! as HTMLElement;
  fireEvent.click(within(sidebar).getByRole("button", { name: "help.md" }));
  fireEvent.click(within(sidebar).getByRole("button", { name: "docs" }));
  const remove = within(sidebar).getByRole("button", {
    name: "common.remove: zzz.md",
  });
  remove.focus();
  fireEvent.click(remove);
  expect(document.activeElement).not.toBe(document.body);
  expect(document.activeElement?.isConnected).toBe(true);
});
