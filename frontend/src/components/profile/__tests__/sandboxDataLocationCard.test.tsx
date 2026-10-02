/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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
  vi.resetAllMocks();
});

test("failed location read keeps the section and can recover", async () => {
  mocks.readSandboxDataLocation
    .mockRejectedValueOnce(new Error("no shell"))
    .mockResolvedValueOnce(DEFAULT_LOCATION);
  render(<SandboxDataLocationCard />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/failed/i);
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(
    await screen.findByRole("button", { name: /change location/i }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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

  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  await waitFor(() => expect(mocks.pickSandboxDirectory).toHaveBeenCalled());

  // 确认面板：所选路径 + 迁移开关默认开
  expect(await screen.findByText(/E:\\sandbox/)).toBeVisible();
  const migrate = screen.getByRole("checkbox") as HTMLInputElement;
  expect(migrate.checked).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: /save and move/i }));

  await waitFor(() =>
    expect(mocks.setSandboxDataLocation).toHaveBeenCalledWith(
      "E:\\sandbox",
      true,
    ),
  );
  // 保存成功：重启引导条 + 立即重启按钮
  expect(await screen.findByText(/restart the app to apply/i)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /restart now/i }));
  await waitFor(() => expect(mocks.relaunch).toHaveBeenCalled());
});

test("cancel from the picker does not open the confirm panel", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue(null);
  render(<SandboxDataLocationCard />);

  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  await waitFor(() => expect(mocks.pickSandboxDirectory).toHaveBeenCalled());
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

  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
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

test("save errors remain visible on the confirm panel", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue("E:\\sandbox");
  mocks.setSandboxDataLocation.mockRejectedValue(
    "new sandbox home must not overlap the current one",
  );
  render(<SandboxDataLocationCard />);

  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: /save and move/i }),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(/failed/i);
  expect(screen.getByRole("alert")).toHaveTextContent(/must not overlap/i);
  expect(screen.getByRole("button", { name: /save and move/i })).toBeVisible();
});

test("saving freezes migration and cancel while focus stays on the section", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue("E:\\sandbox");
  mocks.setSandboxDataLocation.mockImplementationOnce(
    () => new Promise(() => {}),
  );
  const { container } = render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  const apply = await screen.findByRole("button", { name: /save and move/i });
  apply.focus();
  fireEvent.click(apply);
  expect(screen.getByRole("checkbox")).toBeDisabled();
  expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  expect(container.querySelector("[data-sandbox-data-location]")).toHaveFocus();
});

test("cancelled failed save cannot retry an old directory after a new pick", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory
    .mockResolvedValueOnce("E:\\sandbox")
    .mockResolvedValueOnce("F:\\projects");
  mocks.setSandboxDataLocation
    .mockRejectedValueOnce(new Error("overlap"))
    .mockResolvedValueOnce(undefined);
  render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: /save and move/i }),
  );
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
  fireEvent.click(screen.getByRole("button", { name: /change location/i }));
  await screen.findByText(/F:\\projects/);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /retry/i }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /save and move/i }));
  await screen.findByRole("button", { name: /restart now/i });
  expect(mocks.setSandboxDataLocation).toHaveBeenLastCalledWith(
    "F:\\projects",
    true,
  );
});

test("closing during a save suppresses its late success notification", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue("E:\\sandbox");
  let resolve!: () => void;
  mocks.setSandboxDataLocation.mockImplementationOnce(
    () =>
      new Promise<void>((done) => {
        resolve = done;
      }),
  );
  const { unmount } = render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: /save and move/i }),
  );
  await waitFor(() => expect(mocks.setSandboxDataLocation).toHaveBeenCalled());
  unmount();
  await act(async () => resolve());
  expect(mocks.toastSuccess).not.toHaveBeenCalled();
});

test("directory picker failure is visible and retry opens the picker again", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory
    .mockRejectedValueOnce(new Error("dialog unavailable"))
    .mockResolvedValueOnce("E:\\sandbox");
  render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(
    await screen.findByRole("button", { name: /save and move/i }),
  ).toBeVisible();
});

test("restart failure stays beside the saved change and retries only restart", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(DEFAULT_LOCATION);
  mocks.pickSandboxDirectory.mockResolvedValue("E:\\sandbox");
  mocks.setSandboxDataLocation.mockResolvedValue(undefined);
  mocks.relaunch
    .mockRejectedValueOnce(new Error("restart unavailable"))
    .mockResolvedValueOnce(undefined);
  render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: /save and move/i }),
  );
  fireEvent.click(await screen.findByRole("button", { name: /restart now/i }));
  await screen.findByRole("alert");
  expect(screen.getByText(/restart the app to apply/i)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
  expect(mocks.setSandboxDataLocation).toHaveBeenCalledTimes(1);
  expect(mocks.relaunch).toHaveBeenCalledTimes(2);
});

test("customized root offers reset to default", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(CUSTOMIZED_LOCATION);
  mocks.clearSandboxDataLocation.mockResolvedValue(undefined);
  render(<SandboxDataLocationCard />);

  expect(await screen.findByText("Custom")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /reset to default/i }));

  await waitFor(() =>
    expect(mocks.clearSandboxDataLocation).toHaveBeenCalled(),
  );
  // 恢复默认同样进入重启引导（数据不搬回文案）
  expect(
    await screen.findByText(/existing data stays where it is/i),
  ).toBeVisible();
});

test("picking a new directory discards a failed reset before opening the dialog", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(CUSTOMIZED_LOCATION);
  mocks.clearSandboxDataLocation.mockRejectedValue(
    new Error("override is locked"),
  );
  mocks.pickSandboxDirectory.mockImplementation(() => new Promise(() => {}));
  render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /reset to default/i }),
  );
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: /change location/i }));
  expect(
    screen.queryByRole("button", { name: /retry/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /reset to default/i }),
  ).toBeDisabled();
});

test("reset failure remains visible and retries reset without moving existing data", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(CUSTOMIZED_LOCATION);
  mocks.clearSandboxDataLocation
    .mockRejectedValueOnce(new Error("override is locked"))
    .mockResolvedValueOnce(undefined);
  render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /reset to default/i }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    /override is locked/i,
  );
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(
    await screen.findByText(/existing data stays where it is/i),
  ).toBeVisible();
  expect(mocks.setSandboxDataLocation).not.toHaveBeenCalled();
});

test("resetting discards a failed picker before the native reset starts", async () => {
  mocks.readSandboxDataLocation.mockResolvedValue(CUSTOMIZED_LOCATION);
  mocks.pickSandboxDirectory.mockRejectedValue(new Error("dialog unavailable"));
  mocks.clearSandboxDataLocation.mockImplementation(
    () => new Promise(() => {}),
  );
  render(<SandboxDataLocationCard />);
  fireEvent.click(
    await screen.findByRole("button", { name: /change location/i }),
  );
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: /reset to default/i }));
  expect(
    screen.queryByRole("button", { name: /retry/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /change location/i }),
  ).toBeDisabled();
});
