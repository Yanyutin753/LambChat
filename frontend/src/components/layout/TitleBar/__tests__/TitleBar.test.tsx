/** @vitest-environment jsdom */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  minimizeWindow: vi.fn(async () => undefined),
  toggleMaximizeWindow: vi.fn(async () => undefined),
  closeWindow: vi.fn(async () => undefined),
  queryWindowMaximized: vi.fn(async () => false),
  subscribeWindowResized: vi.fn(async () => () => undefined),
}));

vi.mock("../../../../services/tauri/windowControls", () => mocks);

import { TitleBar } from "../TitleBar";
import { NavigationHistoryProvider } from "../../../../hooks/useNavigationHistory";
import type { UpdateState } from "../../../../types";

afterEach(cleanup);

const idleUpdateState: UpdateState = {
  available: false,
  version: null,
  releaseNotes: null,
  releaseUrl: null,
  releaseAssets: [],
  publishedAt: null,
  downloading: false,
  progress: 0,
  contentLength: 0,
  downloaded: 0,
  readyToInstall: false,
  error: null,
  linuxInstallSource: null,
};

/** 手动导航入口：由测试显式点击触发 push，避免 effect 重入 */
function NavigateButton({ to }: { to: string }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      data-testid={`go-${to.replace(/\//g, "")}`}
      onClick={() => navigate(to)}
    >
      go
    </button>
  );
}

function renderTitleBar(
  os: "windows" | "linux" | "mac",
  withNavHelper = false,
) {
  return render(
    <MemoryRouter initialEntries={["/chat"]}>
      <NavigationHistoryProvider>
        {withNavHelper && <NavigateButton to="/settings" />}
        <Routes>
          <Route path="/chat" element={<div>chat-page</div>} />
          <Route path="/settings" element={<div>settings-page</div>} />
        </Routes>
        <TitleBar
          os={os}
          updateState={idleUpdateState}
          onInstallUpdate={() => undefined}
          onSkipVersion={() => undefined}
        />
      </NavigationHistoryProvider>
    </MemoryRouter>,
  );
}

test("windows titlebar shows brand, nav and window controls", () => {
  renderTitleBar("windows");
  expect(screen.getByText("LambChat")).toBeTruthy();
  expect(screen.getByRole("button", { name: "后退" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "前进" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "最小化" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "最大化" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "关闭" })).toBeTruthy();
});

test("mac titlebar keeps nav but drops brand and custom window controls", () => {
  renderTitleBar("mac");
  expect(screen.queryByText("LambChat")).toBeNull();
  expect(screen.getByRole("button", { name: "后退" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "前进" })).toBeTruthy();
  // 红绿灯为原生控件，自绘按钮不应出现
  expect(screen.queryByRole("button", { name: "最小化" })).toBeNull();
  expect(screen.queryByRole("button", { name: "关闭" })).toBeNull();
});

test("nav buttons start disabled and unlock after a push", async () => {
  renderTitleBar("windows", true);
  const back = screen.getByRole("button", { name: "后退" });
  expect(back).toBeDisabled();
  expect(screen.getByRole("button", { name: "前进" })).toBeDisabled();

  fireEvent.click(screen.getByTestId("go-settings"));
  await waitFor(() => expect(back).not.toBeDisabled());
  expect(screen.getByRole("button", { name: "前进" })).toBeDisabled();

  fireEvent.click(back);
  expect(await screen.findByText("chat-page")).toBeTruthy();
});

test("window control buttons drive the window control service", async () => {
  renderTitleBar("windows");
  fireEvent.click(screen.getByRole("button", { name: "最小化" }));
  await waitFor(() => expect(mocks.minimizeWindow).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  await waitFor(() => expect(mocks.closeWindow).toHaveBeenCalledTimes(1));
});

test("drag region spans the flexible middle area", () => {
  renderTitleBar("linux");
  const drag = document.querySelector("[data-tauri-drag-region]");
  expect(drag).toBeTruthy();
  // 拖拽区必须是 flex 弹性占位，否则窗口抓不住
  expect(drag?.className).toContain("flex-1");
});
