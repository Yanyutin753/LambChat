/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import appI18n, { i18nReady } from "../../../i18n";
import { SkillForm } from "../SkillForm";

beforeAll(async () => {
  await i18nReady;
  await appI18n.loadLanguages(["zh"]);
});

vi.mock("../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
afterEach(cleanup);

function openFullscreen() {
  const save = vi.fn().mockResolvedValue(true);
  render(
    <I18nextProvider i18n={appI18n.cloneInstance({ lng: "zh" })}>
      <SkillForm onSave={save} onCancel={() => {}} />
    </I18nextProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "全屏编辑器" }));
  const header = screen.getByRole("button", {
    name: "退出全屏",
  }).parentElement!;
  return { save, header };
}

test("fullscreen find shares the file actions and keeps the native editor search", async () => {
  const { header } = openFullscreen();
  const search = within(header).getByRole("button", { name: "搜索" });
  expect(screen.getAllByRole("button", { name: "搜索" })).toHaveLength(1);
  expect(document.querySelector(".code-editor-toolbar")).toBeNull();
  await waitFor(() => expect(search).toBeEnabled());
  fireEvent.click(search);
  const query = await screen.findByRole("textbox", { name: "查找" });
  expect(query).toHaveFocus();
  expect(screen.getByRole("textbox", { name: "替换" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭", exact: true }));
  expect(screen.getByRole("textbox", { name: "SKILL.md" })).toHaveFocus();
  expect(
    screen.getByRole("dialog", { name: "全屏编辑器" }),
  ).toBeInTheDocument();
});

test("fullscreen file creation focuses an inline path and Enter starts editing without saving", async () => {
  const { header, save } = openFullscreen();
  fireEvent.click(within(header).getByRole("button", { name: "添加文件" }));
  const path = screen.getByRole("textbox", { name: "文件路径" });
  expect(path).toHaveFocus();
  fireEvent.change(path, { target: { value: "scripts/report.py" } });
  fireEvent.keyDown(path, { key: "Enter", code: "Enter" });
  expect(screen.queryByRole("textbox", { name: "文件路径" })).toBeNull();
  await waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: "scripts/report.py" }),
    ).toHaveFocus(),
  );
  expect(
    screen.getByRole("button", { name: "scripts/report.py" }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(save).not.toHaveBeenCalled();
});

test("fullscreen rejects an existing path and retains the naming field and draft", () => {
  const { header, save } = openFullscreen();
  fireEvent.click(within(header).getByRole("button", { name: "添加文件" }));
  const path = screen.getByRole("textbox", { name: "文件路径" });
  fireEvent.change(path, { target: { value: "SKILL.md" } });
  fireEvent.keyDown(path, { key: "Enter", code: "Enter" });
  expect(path).toHaveFocus();
  expect(path).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByRole("alert")).toHaveTextContent("文件路径不能重复");
  expect(save).not.toHaveBeenCalled();
});
