/** @vitest-environment jsdom */

// 机器管理卡：离线机置灰保留（记忆层）、last_seen 展示、忘记离线机操作。

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

const mocks = vi.hoisted(() => ({
  getStatus: vi.fn(),
  listMachines: vi.fn(),
  setDefaultMachine: vi.fn(),
  renameMachine: vi.fn(),
  forgetMachine: vi.fn(),
}));

vi.mock("../../../services/api/sandbox", () => ({
  sandboxApi: { getStatus: mocks.getStatus },
  sandboxApiMachines: {
    listMachines: mocks.listMachines,
    setDefaultMachine: mocks.setDefaultMachine,
    renameMachine: mocks.renameMachine,
    forgetMachine: mocks.forgetMachine,
  },
  machinePlatformLabel: (platform: string) =>
    ({ win32: "Windows", linux: "Linux" })[platform] ?? platform,
}));

vi.mock("react-hot-toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { SandboxMachinesCard } from "../SandboxMachinesCard";
import { _resetSandboxStatusStoreForTests } from "../../../stores/sandboxStatusStore";

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
  mocks.getStatus.mockResolvedValue({ online: true });
  mocks.forgetMachine.mockResolvedValue(undefined);
  mocks.listMachines.mockResolvedValue({
    machines: [
      {
        machine_id: "srv1",
        name: "PrimaryServer",
        platform: "linux",
        version: "0.4.0",
        confirm_policy: "all",
        online: true,
        last_seen: Date.now() / 1000,
      },
      {
        machine_id: "pc1",
        name: "Old PC",
        platform: "win32",
        version: "0.3.0",
        confirm_policy: "all",
        online: false,
        last_seen: Date.now() / 1000 - 3600,
      },
    ],
    default_machine_id: "srv1",
  });
  _resetSandboxStatusStoreForTests();
});

test("online machines show green dot, offline machines greyed with last-seen and forget", async () => {
  render(<SandboxMachinesCard />);
  await waitFor(() =>
    expect(screen.getByText("Server")).toBeInTheDocument(),
  );

  const onlineRow = screen.getByText("PrimaryServer").closest("div");
  expect(onlineRow?.querySelector("span")?.className).toContain("bg-green-500");

  // 离线机：置灰点 + 离线徽标 + 相对时间
  expect(screen.getByText("Old PC")).toBeInTheDocument();
  const offlineRow = screen.getByText("Old PC").closest("div");
  expect(offlineRow?.querySelector("span")?.className).toContain("bg-theme-border-hover");
  expect(screen.getByText(/offline/i)).toBeInTheDocument();
  expect(screen.getByTestId("last-seen-pc1").textContent).toMatch(/1h|h/);

  // 离线机提供忘记按钮，在线机没有
  expect(screen.getByTestId("forget-pc1")).toBeInTheDocument();
  expect(screen.queryByTestId("forget-srv1")).not.toBeInTheDocument();
});

test("each machine row renders exactly one rename button and one platform label", async () => {
  render(<SandboxMachinesCard />);
  await waitFor(() =>
    expect(screen.getByText("PrimaryServer")).toBeInTheDocument(),
  );

  for (const [name, platform] of [
    ["PrimaryServer", "Linux"],
    ["Old PC", "Windows"],
  ] as const) {
    const row = screen.getByText(name).closest("div");
    expect(row?.textContent?.match(new RegExp(platform, "g"))?.length).toBe(1);
    expect(row?.querySelectorAll('button[title="Rename"]').length).toBe(1);
  }
});

test("forget calls the API then refreshes presence state", async () => {
  window.confirm = vi.fn(() => true);
  render(<SandboxMachinesCard />);
  await waitFor(() => expect(screen.getByTestId("forget-pc1")).toBeInTheDocument());

  fireEvent.click(screen.getByTestId("forget-pc1"));
  await waitFor(() =>
    expect(mocks.forgetMachine).toHaveBeenCalledWith("pc1"),
  );
});
