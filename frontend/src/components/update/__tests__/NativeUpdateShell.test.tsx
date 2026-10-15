/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import NativeUpdateShell from "../NativeUpdateShell";

const update = vi.hoisted(() => ({
  state: { available: true },
  showDialog: true,
  setShowDialog: vi.fn(),
  startUpdate: vi.fn(),
  skipThisVersion: vi.fn(),
}));
vi.mock("../../../hooks/useAutoUpdate", () => ({ useAutoUpdate: () => update }));
vi.mock("../UpdateDialog", () => ({
  UpdateDialog: ({ platform, onUpgrade, onSkipVersion, onDismiss }: {
    platform: string;
    onUpgrade: () => void;
    onSkipVersion: () => void;
    onDismiss: () => void;
  }) => (
    <div role="dialog" aria-label={platform}>
      <button onClick={onUpgrade}>Install</button>
      <button onClick={onSkipVersion}>Skip</button>
      <button onClick={onDismiss}>Dismiss</button>
    </div>
  ),
}));
vi.mock("../../layout/TitleBar/DesktopTitlebarFrame", () => ({
  DesktopTitlebarFrame: ({ os, children, updateState, onInstallUpdate, onSkipVersion }: {
    os: string;
    children: ReactNode;
    updateState: { available: boolean };
    onInstallUpdate: () => void;
    onSkipVersion: () => void;
  }) => (
    <div aria-label={os}>
      {updateState.available && <button onClick={onInstallUpdate}>Titlebar install</button>}
      <button onClick={onSkipVersion}>Titlebar skip</button>
      {children}
    </div>
  ),
}));
beforeEach(() => {
  vi.clearAllMocks();
  update.state.available = true;
  update.showDialog = true;
});

test.each(["android", "ios"] as const)("%s preserves update actions and route content", async (platform) => {
  render(<NativeUpdateShell platform={platform} titlebarOs={null}>Routes</NativeUpdateShell>);
  await screen.findByRole("dialog", { name: platform });
  expect(screen.getByText("Routes")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Install"));
  fireEvent.click(screen.getByText("Skip"));
  fireEvent.click(screen.getByText("Dismiss"));
  expect(update.startUpdate).toHaveBeenCalledOnce();
  expect(update.skipThisVersion).toHaveBeenCalledOnce();
  expect(update.setShowDialog).toHaveBeenCalledWith(false);
});

test("desktop retains titlebar update actions and avoids the mobile dialog", async () => {
  render(<NativeUpdateShell platform="tauri" titlebarOs="mac">Routes</NativeUpdateShell>);
  fireEvent.click(await screen.findByText("Titlebar install"));
  fireEvent.click(screen.getByText("Titlebar skip"));
  expect(screen.getByText("Routes")).toBeInTheDocument();
  expect(update.startUpdate).toHaveBeenCalledOnce();
  expect(update.skipThisVersion).toHaveBeenCalledOnce();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test.each(["unavailable", "dismissed"])("mobile keeps routes visible with an %s update", (condition) => {
  update.state.available = condition !== "unavailable";
  update.showDialog = condition !== "dismissed";
  render(<NativeUpdateShell platform="android" titlebarOs={null}>Routes</NativeUpdateShell>);
  expect(screen.getByText("Routes")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).toBeNull();
});
