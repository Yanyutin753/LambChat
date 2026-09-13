/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

const mocks = vi.hoisted(() => ({
  readSandboxDataLocation: vi.fn(),
  setSandboxDataLocation: vi.fn(),
  clearSandboxDataLocation: vi.fn(),
  pickSandboxDirectory: vi.fn(),
  relaunch: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("../../../services/tauri/sandboxShell", () => ({
  readSandboxDataLocation: mocks.readSandboxDataLocation,
  setSandboxDataLocation: mocks.setSandboxDataLocation,
  clearSandboxDataLocation: mocks.clearSandboxDataLocation,
  pickSandboxDirectory: mocks.pickSandboxDirectory,
}));

vi.mock("@tauri-apps/plugin-process", () => ({
  relaunch: mocks.relaunch,
}));

vi.mock("react-hot-toast", () => ({
  toast: { success: mocks.toastSuccess, error: mocks.toastError },
}));

import { SandboxDataLocationCard } from "../SandboxDataLocationCard";

const DEFAULT_LOCATION = {
  root: "C:\\Users\\dev\\.lambchat",
  customized: false,
  overrideConfigured: false,
};

const CUSTOMIZED_LOCATION = {
  root: "D:\\lambchat",
  customized: true,
  overrideConfigured: true,
};

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
});

test("renders nothing when the location cannot be read", async () => {
  mocks.readSandboxDataLocation.mockRejectedValue(new Error("no shell"));
  const { container } = render(<SandboxDataLocationCard />);
  await waitFor(() =>
    expect(mocks.readSandboxDataLocation).toHaveBeenCalled(),
  );
  expect(container.firstChild).toBeNull();
});

test("shows the root path with the default badge", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  render(<SandboxDataLocationCard />);

  expect(await screen.findByText(/C:\\Users\\dev\\.lambchat/)).toBeVisible();
  expect(screen.getByText("Default")).toBeVisible();
  // 缺省根：没有"恢复默认"，只有"更改位置"
  expect(
    screen.queryByRole("button", { name: /reset to default/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /change location/i }),
  ).toBeVisible();
});

test("change flow: pick → confirm with migration → save → restart banner", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue("E:\\sandbox");
  mocks.setSandboxDataLocation.mockResolvedValue(undefined);
  render(<SandboxDataLocationCard />);

  fireEvent.click(await screen.findByRole("button", { name: /change location/i }));
  await waitFor(() =>
    expect(mocks.pickSandboxDirectory).toHaveBeenCalled(),
  );

  // 确认面板：所选路径 + 迁移开关默认开
  expect(await screen.findByText(/E:\\sandbox/)).toBeVisible();
  const migrate = screen.getByRole("checkbox") as HTMLInputElement;
  expect(migrate.checked).toBe(true);
  fireEvent.click(
    screen.getByRole("button", { name: /save and move/i }),
  );

  await waitFor(() =>
    expect(mocks.setSandboxDataLocation).toHaveBeenCalledWith(
      "E:\\sandbox",
      true,
    ),
  );
  // 保存成功：重启引导条 + 立即重启按钮
  expect(
    await screen.findByText(/restart the app to apply/i),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /restart now/i }));
  await waitFor(() => expect(mocks.relaunch).toHaveBeenCalled());
});

test("cancel from the picker does not open the confirm panel", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue(null);
  render(<SandboxDataLocationCard />);

  fireEvent.click(await screen.findByRole("button", { name: /change location/i }));
  await waitFor(() =>
    expect(mocks.pickSandboxDirectory).toHaveBeenCalled(),
  );
  expect(
    screen.queryByRole("button", { name: /save and move/i }),
  ).not.toBeInTheDocument();
  expect(mocks.setSandboxDataLocation).not.toHaveBeenCalled();
});

test("unchecking migration saves without moving data", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue("E:\\sandbox");
  mocks.setSandboxDataLocation.mockResolvedValue(undefined);
  render(<SandboxDataLocationCard />);

  fireEvent.click(await screen.findByRole("button", { name: /change location/i }));
  await screen.findByText(/E:\\sandbox/);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

  await waitFor(() =>
    expect(mocks.setSandboxDataLocation).toHaveBeenCalledWith(
      "E:\\sandbox",
      false,
    ),
  );
});

test("save errors surface a toast and stay on the confirm panel", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue("E:\\sandbox");
  mocks.setSandboxDataLocation.mockRejectedValue(
    "new sandbox home must not overlap the current one",
  );
  render(<SandboxDataLocationCard />);

  fireEvent.click(await screen.findByRole("button", { name: /change location/i }));
  fireEvent.click(
    await screen.findByRole("button", { name: /save and move/i }),
  );

  await waitFor(() => expect(mocks.toastError).toHaveBeenCalled());
  expect(
    screen.getByRole("button", { name: /save and move/i }),
  ).toBeVisible();
});

test("customized root offers reset to default", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(CUSTOMIZED_LOCATION);
  mocks.clearSandboxDataLocation.mockResolvedValue(undefined);
  render(<SandboxDataLocationCard />);

  expect(await screen.findByText("Custom")).toBeVisible();
  fireEvent.click(
    screen.getByRole("button", { name: /reset to default/i }),
  );

  await waitFor(() =>
    expect(mocks.clearSandboxDataLocation).toHaveBeenCalled(),
  );
  // 恢复默认同样进入重启引导（数据不搬回文案）
  expect(
    await screen.findByText(/existing data stays where it is/i),
  ).toBeVisible();
});
