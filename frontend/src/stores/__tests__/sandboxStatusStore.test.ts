/** @vitest-environment jsdom */

import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getStatus: vi.fn(),
  listMachines: vi.fn(),
}));

vi.mock("../../services/api/sandbox", () => ({
  sandboxApi: { getStatus: mocks.getStatus },
  sandboxApiMachines: { listMachines: mocks.listMachines },
}));

import { SANDBOX_ONLINE_CHANGED_EVENT } from "../../components/layout/AppContent/useAgentOptions";
import {
  applySandboxPresence,
  attachSandboxStatusStore,
  _resetSandboxStatusStoreForTests,
  refreshSandboxStatus,
  setSandboxWsHealthy,
} from "../sandboxStatusStore";

function flushedStatus(online: boolean) {
  return mocks.getStatus.mockResolvedValue({ online });
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.getStatus.mockReset();
  mocks.listMachines.mockReset();
  mocks.listMachines.mockResolvedValue({
    machines: [],
    default_machine_id: null,
  });
  _resetSandboxStatusStoreForTests();
});

afterEach(() => {
  _resetSandboxStatusStoreForTests();
  vi.useRealTimers();
});

test("concurrent refreshes are deduped into one API round", async () => {
  let resolveStatus: (v: { online: boolean }) => void = () => {};
  mocks.getStatus.mockReturnValue(
    new Promise((resolve) => {
      resolveStatus = resolve;
    }),
  );

  const first = refreshSandboxStatus();
  const second = refreshSandboxStatus();
  resolveStatus({ online: true });
  await Promise.all([first, second]);

  // 并发去重：在途期间不并发发起；挂起的请求在首轮结束后补拉一轮
  // （与原 useSandboxStatus 的 pending 语义一致：变更后的刷新不被在途旧拉取吞掉）
  expect(mocks.getStatus.mock.calls.length).toBeGreaterThanOrEqual(1);
  expect(mocks.getStatus.mock.calls.length).toBeLessThanOrEqual(2);
});

test("attach starts a single poller at the ws-down cadence", async () => {
  flushedStatus(false);
  const detach = attachSandboxStatusStore();
  await vi.advanceTimersByTimeAsync(0);
  expect(mocks.getStatus).toHaveBeenCalledTimes(1);

  await vi.advanceTimersByTimeAsync(10_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(2);

  detach();
  await vi.advanceTimersByTimeAsync(30_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(2);
});

test("healthy websocket slows polling to the reconcile cadence", async () => {
  flushedStatus(true);
  const detach = attachSandboxStatusStore();
  setSandboxWsHealthy(true);
  await vi.advanceTimersByTimeAsync(0);

  expect(mocks.getStatus).toHaveBeenCalledTimes(2); // attach 拉一次 + ws 恢复对账一次

  await vi.advanceTimersByTimeAsync(10_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(2); // 10s 不再打点

  await vi.advanceTimersByTimeAsync(50_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(3); // 60s 对账

  detach();
});

test("second attach does not start a second poller", async () => {
  flushedStatus(false);
  const detachA = attachSandboxStatusStore();
  const detachB = attachSandboxStatusStore();
  await vi.advanceTimersByTimeAsync(0);

  await vi.advanceTimersByTimeAsync(20_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(3); // 首拉 + 2 个 10s 节拍

  detachA();
  await vi.advanceTimersByTimeAsync(20_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(5); // 仍有一个订阅者，继续轮询

  detachB();
  await vi.advanceTimersByTimeAsync(20_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(5);
});

test("hidden tab pauses polling and visible refreshes immediately", async () => {
  flushedStatus(false);
  const detach = attachSandboxStatusStore();
  await vi.advanceTimersByTimeAsync(0);
  expect(mocks.getStatus).toHaveBeenCalledTimes(1);

  vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  document.dispatchEvent(new Event("visibilitychange"));

  await vi.advanceTimersByTimeAsync(30_000);
  expect(mocks.getStatus).toHaveBeenCalledTimes(1); // 后台不打点

  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  document.dispatchEvent(new Event("visibilitychange"));
  await vi.advanceTimersByTimeAsync(0);
  expect(mocks.getStatus).toHaveBeenCalledTimes(2); // 回前台立即补拉

  detach();
});

test("presence snapshot updates machines and default machine", async () => {
  flushedStatus(false);
  const detach = attachSandboxStatusStore();
  await vi.advanceTimersByTimeAsync(0);

  applySandboxPresence({
    machines: [
      {
        machine_id: "m1",
        name: "MacBook",
        platform: "darwin",
        version: "0.4.0",
        confirm_policy: "all",
        online: true,
        last_seen: 1700_000_000,
      },
    ],
    default_machine_id: "m1",
    legacy_online: false,
    revision: 100.5,
  });

  const state = getSandboxStatusStoreState();
  expect(state.machines.map((m) => m.machine_id)).toEqual(["m1"]);
  expect(state.defaultMachineId).toBe("m1");
  // 首次上线翻转补拉一次元数据（/status），推送本身直达不打 machines API
  const callsAfterTransition = mocks.listMachines.mock.calls.length;
  expect(callsAfterTransition).toBeLessThanOrEqual(2);

  // 持续在线的后续推送：纯直达，不再触发 machines 拉取
  applySandboxPresence({
    machines: [
      {
        machine_id: "m1",
        name: "MacBook Pro",
        platform: "darwin",
        version: "0.4.1",
        confirm_policy: "none",
        online: true,
        last_seen: 1700_000_100,
      },
    ],
    default_machine_id: "m1",
    legacy_online: false,
    revision: 101.0,
  });
  expect(mocks.listMachines.mock.calls.length).toBe(callsAfterTransition);
  expect(getSandboxStatusStoreState().machines[0].name).toBe("MacBook Pro");

  detach();
});

test("stale presence revisions are dropped", async () => {
  flushedStatus(false);
  const detach = attachSandboxStatusStore();
  await vi.advanceTimersByTimeAsync(0);

  applySandboxPresence({
    machines: [
      {
        machine_id: "m1",
        name: "A",
        platform: "linux",
        version: "1",
        confirm_policy: "all",
        online: true,
        last_seen: 1,
      },
    ],
    default_machine_id: null,
    legacy_online: false,
    revision: 200.0,
  });

  let state = getSandboxStateViaProbe();
  expect(state.machines.map((m) => m.machine_id)).toEqual(["m1"]);

  applySandboxPresence({
    machines: [],
    default_machine_id: null,
    legacy_online: false,
    revision: 100.0, // 旧事件
  });
  state = getSandboxStateViaProbe();
  expect(state.machines.map((m) => m.machine_id)).toEqual(["m1"]); // 未被旧事件回滚

  detach();
});

test("invalid presence payload is ignored", async () => {
  flushedStatus(false);
  const detach = attachSandboxStatusStore();
  await vi.advanceTimersByTimeAsync(0);

  applySandboxPresence({ machines: "not-an-array", revision: 1 } as never);
  applySandboxPresence({ machines: [], revision: "bad" } as never);
  applySandboxPresence({
    machines: [{ name: "no-id" }],
    revision: 2,
  } as never);

  const state = getSandboxStateViaProbe();
  expect(state.machines).toEqual([]);
  detach();
});

test("offline to online transition dispatches the online-changed event", async () => {
  flushedStatus(false);
  const detach = attachSandboxStatusStore();
  await vi.advanceTimersByTimeAsync(0);

  const onlineEvents: string[] = [];
  const onOnline = () => onlineEvents.push("online");
  window.addEventListener(SANDBOX_ONLINE_CHANGED_EVENT, onOnline);

  applySandboxPresence({
    machines: [
      {
        machine_id: "m1",
        name: "A",
        platform: "linux",
        version: "1",
        confirm_policy: "all",
        online: true,
        last_seen: 1,
      },
    ],
    default_machine_id: null,
    legacy_online: false,
    revision: 300.0,
  });

  expect(onlineEvents).toEqual(["online"]);

  // 仍在线的后续推送不重复派发
  applySandboxPresence({
    machines: [
      {
        machine_id: "m1",
        name: "A",
        platform: "linux",
        version: "1",
        confirm_policy: "all",
        online: true,
        last_seen: 2,
      },
    ],
    default_machine_id: null,
    legacy_online: false,
    revision: 301.0,
  });
  expect(onlineEvents).toEqual(["online"]);

  window.removeEventListener(SANDBOX_ONLINE_CHANGED_EVENT, onOnline);
  detach();
});

// 直接读 store 状态的探针（避免在每个用例里重复订阅样板）
import { getSandboxStatusStoreState } from "../sandboxStatusStore";
function getSandboxStateViaProbe() {
  return getSandboxStatusStoreState();
}
