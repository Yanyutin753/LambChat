/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test } from "vitest";
import zh from "../../../../../i18n/locales/zh.json";
import { ComputerUseItem } from "../ComputerUseItem";
import {
  closeAllPersistentToolPanels,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

const i18n = createInstance();
await i18n.init({
  lng: "zh",
  resources: { zh: { translation: zh } },
  interpolation: { escapeValue: false },
});
afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
});

function show(props: React.ComponentProps<typeof ComputerUseItem>) {
  const view = render(
    <I18nextProvider i18n={i18n}>
      <ComputerUseItem {...props} />
    </I18nextProvider>,
  );
  fireEvent.click(view.getByRole("button"));
  const panel = render(
    <I18nextProvider i18n={i18n}>
      {getPersistentToolPanelState()!.children}
    </I18nextProvider>,
  );
  return { view: within(view.container), panel: within(panel.container) };
}

test("collapsed control identifies the localized action and target", () => {
  const { view } = show({
    args: { action: "click", name: "VSCode", index: 0 },
    result: { ok: true },
    success: true,
  });
  expect(view.getByRole("button").textContent).toContain("点击");
  expect(view.getByRole("button").textContent).toContain("VSCode");
  expect(view.getByRole("button").textContent).toContain("#0");
});

test("historical status exposes platform and both permission states", () => {
  const { panel } = show({
    args: { action: "status" },
    result:
      "{'platform': 'darwin', 'ready': True, 'accessibility': 'granted', 'screen_recording': 'unknown'}",
    success: true,
  });
  expect(panel.getByText("macOS")).toBeTruthy();
  expect(panel.getByText("辅助功能")).toBeTruthy();
  expect(panel.getByText("屏幕录制")).toBeTruthy();
  expect(panel.getByText("已授权")).toBeTruthy();
  expect(panel.getByText("未检测")).toBeTruthy();
});

test("state panel displays screenshot, full tree, and zero-valued window ID", () => {
  const { panel } = show({
    args: { action: "state", name: "Editor" },
    result: {
      pid: 42,
      window: { window_id: 0, title: "Main" },
      element_count: 1,
      truncated: true,
      state: "window: Main\n[0] AXButton 'OK'",
      screenshot: {
        mime: "image/png",
        data_b64: "YWJjZA==",
        width: 800,
        height: 600,
      },
    },
    success: true,
  });
  expect(panel.getByRole("img").getAttribute("src")).toBe(
    "data:image/png;base64,YWJjZA==",
  );
  expect(
    panel
      .getAllByText(/\[0\] AXButton/)
      .some((node) => node.textContent === "window: Main\n[0] AXButton 'OK'"),
  ).toBe(true);
  expect(panel.getByText("窗口 ID").nextElementSibling?.textContent).toBe("0");
  expect(panel.getByText(/界面树已截断/)).toBeTruthy();
  expect(
    panel.getByRole("img").parentElement?.parentElement?.textContent,
  ).not.toContain("YWJjZA==");
});

test("daemon errors never show a successful pill", () => {
  const { view, panel } = show({
    args: { action: "state", pid: 42 },
    result: "ERROR dispatch_failed: offline",
    success: true,
  });
  expect(view.getByRole("button").className).toContain("bg-red");
  expect(panel.getByText(/打开 LambChat 桌面端/)).toBeTruthy();
});

test("empty applications have an explicit empty result", () => {
  const { panel } = show({
    args: { action: "apps" },
    result: { apps: [] },
    success: true,
  });
  expect(panel.getByText("未发现应用")).toBeTruthy();
});

test("running control shows a waiting state instead of a blank panel", () => {
  const { panel } = show({
    args: { action: "state", pid: 42 },
    isPending: true,
  });
  expect(panel.getByText("正在执行，等待电脑返回结果…")).toBeTruthy();
});
