/** @vitest-environment jsdom */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { UpdateTitlebarIndicator } from "../UpdateTitlebarIndicator";
import { APP_VERSION } from "../../../../utils/appVersion";
import type { UpdateState } from "../../../../types";

afterEach(cleanup);

function makeState(overrides: Partial<UpdateState> = {}): UpdateState {
  return {
    available: true,
    version: "99.0.0",
    releaseNotes: "## What's Changed\n- 修复了若干问题",
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
    ...overrides,
  };
}

function renderIndicator(
  state: UpdateState,
  handlers: { onInstall?: () => void; onSkipVersion?: () => void } = {},
) {
  return render(
    <UpdateTitlebarIndicator
      state={state}
      onInstall={handlers.onInstall ?? (() => undefined)}
      onSkipVersion={handlers.onSkipVersion ?? (() => undefined)}
    />,
  );
}

test("renders nothing while no update is available", () => {
  const { container } = renderIndicator(makeState({ available: false }));
  expect(container).toBeEmptyDOMElement();
});

test("clicking the icon opens a popover with version transition and notes", () => {
  renderIndicator(makeState());
  fireEvent.click(screen.getByRole("button", { name: /发现新版本/ }));
  const text = document.body.textContent ?? "";
  expect(text).toContain(APP_VERSION);
  expect(text).toContain("99.0.0");
  expect(screen.getByText(/修复了若干问题/)).toBeTruthy();
});

test("downloading phase shows progress and hides the skip action", () => {
  renderIndicator(
    makeState({
      downloading: true,
      progress: 42,
      downloaded: 50,
      contentLength: 100,
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: /正在下载/ }));
  const popover = screen.getByRole("dialog");
  expect(within(popover).getByText(/42%/)).toBeTruthy();
  expect(
    within(popover).queryByRole("button", { name: /跳过此版本/ }),
  ).toBeNull();
  // 下载中主按钮禁用，防重复触发
  expect(
    within(popover).getByRole("button", { name: /正在下载/ }),
  ).toBeDisabled();
});

test("ready-to-install phase offers relaunch wired to onInstall", () => {
  const onInstall = vi.fn();
  renderIndicator(makeState({ readyToInstall: true }), { onInstall });
  fireEvent.click(screen.getByRole("button", { name: /发现新版本/ }));
  fireEvent.click(screen.getByRole("button", { name: /重启并安装/ }));
  expect(onInstall).toHaveBeenCalledTimes(1);
});

test("linux deb/rpm source swaps the primary action to download-and-install", () => {
  renderIndicator(makeState({ linuxInstallSource: "deb" }));
  fireEvent.click(screen.getByRole("button", { name: /发现新版本/ }));
  expect(screen.getByRole("button", { name: /下载并安装/ })).toBeTruthy();
  expect(screen.queryByRole("button", { name: /重启并安装/ })).toBeNull();
});

test("error phase surfaces the message with a retry action", () => {
  const onInstall = vi.fn();
  renderIndicator(makeState({ error: "磁盘空间不足" }), { onInstall });
  fireEvent.click(screen.getByRole("button", { name: /更新失败/ }));
  expect(screen.getByText(/磁盘空间不足/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /重试/ }));
  expect(onInstall).toHaveBeenCalledTimes(1);
});

test("skip-this-version is wired and hidden while downloading", () => {
  const onSkipVersion = vi.fn();
  renderIndicator(makeState(), { onSkipVersion });
  fireEvent.click(screen.getByRole("button", { name: /发现新版本/ }));
  fireEvent.click(screen.getByRole("button", { name: /跳过此版本/ }));
  expect(onSkipVersion).toHaveBeenCalledTimes(1);
});
