/** @vitest-environment jsdom */

import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getStatus: vi.fn(),
}));

vi.mock("../../services/api/sandbox", () => ({
  sandboxApi: { getStatus: mocks.getStatus },
}));

import {
  notifySandboxStatusRefresh,
  useSandboxStatus,
} from "../useSandboxStatus";

function Probe() {
  const { status, statusError } = useSandboxStatus();
  return (
    <div data-testid="probe">
      {JSON.stringify({ status, statusError })}
    </div>
  );
}

beforeEach(() => {
  mocks.getStatus.mockReset();
});

test("fetches status on mount and refetches on the refresh event", async () => {
  mocks.getStatus.mockResolvedValue({ online: false });

  render(<Probe />);
  await waitFor(() => expect(mocks.getStatus).toHaveBeenCalledTimes(1));

  act(() => {
    notifySandboxStatusRefresh();
  });

  await waitFor(() => expect(mocks.getStatus).toHaveBeenCalledTimes(2));
});

test("exposes online status and daemon version from the payload", async () => {
  mocks.getStatus.mockResolvedValue({
    online: true,
    daemon_version: "0.1.0",
  });

  const view = render(<Probe />);
  await waitFor(() =>
    expect(view.getByTestId("probe").textContent).toContain("0.1.0"),
  );
  expect(view.getByTestId("probe").textContent).toContain('"online":true');
  expect(view.getByTestId("probe").textContent).not.toContain(
    '"statusError":"',
  );
});

test("marks unauthorized when the status request rejects with 401", async () => {
  const err = new Error("Unauthorized") as Error & { status?: number };
  err.status = 401;
  mocks.getStatus.mockRejectedValue(err);

  const view = render(<Probe />);
  await waitFor(() =>
    expect(view.getByTestId("probe").textContent).toContain("unauthorized"),
  );
});

test("keeps silent on generic request failures", async () => {
  mocks.getStatus.mockRejectedValue(new Error("network down"));

  const view = render(<Probe />);
  // 初始拉取失败：状态保持未知，错误标记为 failed（区别于 401 unauthorized）
  await waitFor(() =>
    expect(view.getByTestId("probe").textContent).toContain(
      '"statusError":"failed"',
    ),
  );
  expect(view.getByTestId("probe").textContent).toContain('"status":null');
});

test("stops polling after unmount", async () => {
  mocks.getStatus.mockResolvedValue({ online: false });
  const view = render(<Probe />);
  await waitFor(() => expect(mocks.getStatus).toHaveBeenCalledTimes(1));
  view.unmount();

  act(() => {
    notifySandboxStatusRefresh();
  });

  // unmount 后事件监听已清理，不再发起请求
  expect(mocks.getStatus).toHaveBeenCalledTimes(1);
});
