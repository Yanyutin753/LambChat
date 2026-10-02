/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { CodeMirrorViewer } from "../CodeMirrorViewer";
import { SkillEditor } from "../../skill/SkillEditor";
import { I18nextProvider } from "react-i18next";
import appI18n from "../../../i18n";

vi.mock("../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
afterEach(cleanup);

async function renderEditor(
  readOnly: boolean | "skill-preview" = false,
  language = "zh",
) {
  const i18n = appI18n.cloneInstance({ lng: language });
  const change = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      {readOnly === true ? (
        <CodeMirrorViewer filePath="notes.txt" value="alpha alpha" />
      ) : (
        <SkillEditor
          filePath="notes.txt"
          value="alpha alpha"
          onChange={change}
          readOnly={readOnly === "skill-preview"}
        />
      )}
    </I18nextProvider>,
  );
  return change;
}

test("plain file code keeps a floating native find action instead of a toolbar row", () => {
  const { container } = render(
    <I18nextProvider i18n={appI18n.cloneInstance({ lng: "zh" })}>
      <CodeMirrorViewer filePath="notes.txt" value="alpha alpha" />
    </I18nextProvider>,
  );
  expect(container.querySelector(".code-editor-toolbar")).toHaveClass(
    "code-editor-toolbar--floating",
  );
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  expect(screen.getByRole("textbox", { name: "查找" })).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  const editor = screen.getByRole("textbox", { name: "notes.txt" });
  act(() => editor.focus());
  fireEvent.keyDown(editor, { key: "f", code: "KeyF", ctrlKey: true });
  expect(screen.getByRole("textbox", { name: "查找" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(editor).toHaveFocus();
  expect(editor).toHaveTextContent("alpha alpha");
});

test("skill search opens from its button, uses the app language and returns focus on close", async () => {
  const change = await renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  const field = screen.getByRole("textbox", { name: "查找" });
  expect(document.activeElement).toBe(field);
  expect(screen.getByRole("checkbox", { name: "区分大小写" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(screen.queryByRole("textbox", { name: "查找" })).toBeNull();
  expect(document.activeElement).toBe(
    screen.getByRole("textbox", { name: "notes.txt" }),
  );
  expect(change).not.toHaveBeenCalled();
});

test("search replacement edits the draft without submitting its enclosing form", async () => {
  const change = await renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  fireEvent.change(screen.getByRole("textbox", { name: "查找" }), {
    target: { value: "alpha" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "替换" }), {
    target: { value: "beta" },
  });
  const replace = screen.getByRole("button", { name: "全部替换" });
  expect(replace.getAttribute("type")).toBe("button");
  fireEvent.click(replace);
  expect(screen.getByRole("textbox", { name: "notes.txt" }).textContent).toBe(
    "beta beta",
  );
  expect(change).toHaveBeenCalledWith("beta beta", expect.anything());
});

test("read-only code search offers no replacement and leaves Tab available for navigation", async () => {
  await renderEditor(true);
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  expect(screen.getByRole("textbox", { name: "查找" })).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "替换" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  const editor = screen.getByRole("textbox", { name: "notes.txt" });
  expect(document.activeElement).toBe(editor);
  expect(
    fireEvent.keyDown(editor, { key: "Tab", code: "Tab", keyCode: 9 }),
  ).toBe(true);
  expect(editor.textContent).toBe("alpha alpha");
});

test("read-only skill preview returns focus to its code after search closes", async () => {
  await renderEditor("skill-preview");
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(document.activeElement).toBe(
    screen.getByRole("textbox", { name: "notes.txt" }),
  );
});

test("IME candidate Enter and Escape leave the query, panel and draft unchanged", async () => {
  const change = await renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  const field = screen.getByRole("textbox", { name: "查找" });
  fireEvent.change(field, { target: { value: "alpha" } });
  expect(
    fireEvent.keyDown(field, { key: "Enter", keyCode: 13, isComposing: true }),
  ).toBe(true);
  expect(
    fireEvent.keyDown(field, { key: "Escape", keyCode: 27, isComposing: true }),
  ).toBe(true);
  expect(screen.getByRole("textbox", { name: "查找" })).toBe(field);
  expect(document.activeElement).toBe(field);
  expect(change).not.toHaveBeenCalled();
});

test.each([
  ["en", "Search", "Find", "Match case"],
  ["ja", "検索", "検索", "大文字と小文字を区別"],
  ["ko", "검색", "찾기", "대소문자 구분"],
  ["ru", "Поиск", "Найти", "Учитывать регистр"],
])(
  "%s search uses the registered locale in the lazy editor",
  async (language, search, find, matchCase) => {
    await renderEditor(true, language);
    fireEvent.click(screen.getByRole("button", { name: search }));
    expect(screen.getByRole("textbox", { name: find })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: matchCase })).toBeTruthy();
  },
);
