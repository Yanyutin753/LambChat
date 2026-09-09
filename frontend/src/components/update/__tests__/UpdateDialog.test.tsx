/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { UpdateDialog } from "../UpdateDialog";
import { APP_VERSION } from "../../../utils/appVersion";
import type { UpdateState } from "../../../types";

afterEach(cleanup);

function makeState(overrides: Partial<UpdateState> = {}): UpdateState {
  return {
    available: true,
    version: "99.0.0",
    releaseNotes: "## What's Changed\n- 修复了若干问题",
    releaseUrl: "https://github.com/example/repo/releases/tag/v99.0.0",
    releaseAssets: [],
    publishedAt: "2026-09-09T00:00:00Z",
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

const baseProps = {
  isOpen: true,
  onUpgrade: () => undefined,
  onSkip: () => undefined,
  onDismiss: () => undefined,
  onSkipVersion: () => undefined,
  platform: "tauri" as const,
};

test("shows the version transition (current → new) like standard updaters", () => {
  render(<UpdateDialog {...baseProps} state={makeState()} />);
  const text = document.body.textContent ?? "";
  expect(text).toContain(APP_VERSION);
  expect(text).toContain("99.0.0");
  // 更新日志渲染
  expect(screen.getByText(/What's Changed/)).toBeTruthy();
  expect(screen.getByText(/修复了若干问题/)).toBeTruthy();
});

test("skip-this-version action is available before download and wired", () => {
  const onSkipVersion = vi.fn();
  render(
    <UpdateDialog {...baseProps} onSkipVersion={onSkipVersion} state={makeState()} />,
  );
  fireEvent.click(screen.getByRole("button", { name: /跳过此版本/ }));
  expect(onSkipVersion).toHaveBeenCalledTimes(1);
});

test("downloading state hides skip actions and shows progress", () => {
  const onSkip = vi.fn();
  const onSkipVersion = vi.fn();
  render(
    <UpdateDialog
      {...baseProps}
      onSkip={onSkip}
      onSkipVersion={onSkipVersion}
      state={makeState({ downloading: true, progress: 42, downloaded: 50, contentLength: 100 })}
    />,
  );
  expect(screen.queryByRole("button", { name: /跳过此版本/ })).toBeNull();
  expect(screen.queryByRole("button", { name: /以后再说/ })).toBeNull();
  expect(screen.getByText(/42%/)).toBeTruthy();
});

test("ready-to-install state shows relaunch button", () => {
  render(
    <UpdateDialog {...baseProps} state={makeState({ readyToInstall: true })} />,
  );
  expect(screen.getByRole("button", { name: /重启并安装/ })).toBeTruthy();
});

test("linux package source (deb/rpm) shows download-and-install button", () => {
  for (const source of ["deb", "rpm"] as const) {
    cleanup();
    render(
      <UpdateDialog
        {...baseProps}
        state={makeState({ linuxInstallSource: source })}
      />,
    );
    expect(screen.getByRole("button", { name: /下载并安装/ })).toBeTruthy();
    // 非 updater 语义：不该出现「重启并安装」或「立即升级」
    expect(screen.queryByRole("button", { name: /重启并安装/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /立即升级/ })).toBeNull();
  }
});

test("unknown linux source falls back to go-to-download button", () => {
  render(
    <UpdateDialog
      {...baseProps}
      state={makeState({ linuxInstallSource: "unknown" })}
    />,
  );
  expect(screen.getByRole("button", { name: /前往下载/ })).toBeTruthy();
  expect(screen.queryByRole("button", { name: /下载并安装/ })).toBeNull();
});

test("appimage source keeps the updater button semantics", () => {
  render(
    <UpdateDialog
      {...baseProps}
      state={makeState({
        linuxInstallSource: "appimage",
        readyToInstall: true,
      })}
    />,
  );
  expect(screen.getByRole("button", { name: /重启并安装/ })).toBeTruthy();
});

test("uses the universal Dialog shell (common dialog component)", () => {
  const source = readFileSync(
    resolve(import.meta.dirname, "../UpdateDialog.tsx"),
    "utf8",
  );
  expect(source).toMatch(/from "\.\.\/common\/Dialog"/);
  // 移动端同款：通用弹窗自带底部弹层（sm 断点前 items-end）
  const dialogSource = readFileSync(
    resolve(import.meta.dirname, "../../common/Dialog.tsx"),
    "utf8",
  );
  expect(dialogSource).toMatch(/items-end sm:items-center/);
  expect(dialogSource).toMatch(/rounded-t-2xl/);
  expect(dialogSource).toMatch(/sm:rounded-xl/);
});
