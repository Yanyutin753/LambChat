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

function GatedProbe({ enabled }: { enabled: boolean }) {
  const { status, statusError } = useSandboxStatus({ enabled });
  return (
    <div data-testid="probe">
      {JSON.stringify({ status, statusError })}
    </div>
  );
}

test("enabled=false does not fetch, poll, or react to refresh events", async () => {
  mocks.getStatus.mockResolvedValue({ online: false });

  const view = render(<GatedProbe enabled={false} />);

  act(() => {
    notifySandboxStatusRefresh();
  });
  // 门控关闭：不拉取、不响应刷新事件
  expect(mocks.getStatus).not.toHaveBeenCalled();

  await new Promise((resolve) => setTimeout(resolve, 30));
  view.unmount();
});

test("enabled toggles polling on and picks up immediately on open", async () => {
  mocks.getStatus.mockResolvedValue({ online: true });

  const view = render(<GatedProbe enabled={false} />);
  expect(mocks.getStatus).not.toHaveBeenCalled();

  // false → true：effect 重跑，立即补拉一次（popover 展开瞬间拿到状态）
  view.rerender(<GatedProbe enabled={true} />);
  await waitFor(() => expect(mocks.getStatus).toHaveBeenCalledTimes(1));

  // 回到 false：不再轮询（刷新事件被门控挡下）
  view.rerender(<GatedProbe enabled={false} />);
  act(() => {
    notifySandboxStatusRefresh();
  });
  expect(mocks.getStatus).toHaveBeenCalledTimes(1);
  view.unmount();
});
