/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  within,
  waitFor,
} from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test, vi } from "vitest";
import * as tokenManager from "../../../../../services/api/tokenManager";
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
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("screenshots load with authentication into revocable blob URLs", async () => {
  vi.spyOn(tokenManager, "getValidAccessToken").mockResolvedValue("test-token");
  const fetch = vi
    .fn()
    .mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(["test"], { type: "image/jpeg" }),
    });
  vi.stubGlobal("fetch", fetch);
  const create = vi.fn().mockReturnValue("blob:private-screenshot");
  const revoke = vi.fn();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: create,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revoke,
  });
  const { panel } = show({
    args: { action: "state" },
    result: {
      screenshot: { url: "/api/upload/file/cua_screenshots/u/s/test.jpg" },
    },
    success: true,
  });
  await waitFor(() =>
    expect(panel.getByRole("img").getAttribute("src")).toBe(
      "blob:private-screenshot",
    ),
  );
  expect(fetch.mock.calls[0][1].headers.get("Authorization")).toBe(
    "Bearer test-token",
  );
  expect(fetch.mock.calls[0][1].cache).toBe("no-store");
  cleanup();
  expect(revoke).toHaveBeenCalledWith("blob:private-screenshot");
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

test("external screenshot URLs never receive the user's access token", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const { panel } = show({
    args: { action: "state" },
    result: {
      screenshot: { url: "https://untrusted.example/api/upload/file/test.jpg" },
    },
    success: true,
  });
  expect(fetch).not.toHaveBeenCalled();
  expect(panel.queryByRole("img")).toBeNull();
});

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
