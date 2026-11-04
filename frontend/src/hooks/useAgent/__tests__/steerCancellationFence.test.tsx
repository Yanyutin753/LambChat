/** @vitest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const { steer, cancelSteer } = vi.hoisted(() => ({
  steer: vi.fn(),
  cancelSteer: vi.fn(),
}));
vi.mock("../../../services/api", () => ({
  sessionApi: { steer, cancelSteer },
}));

import { useSteerQueue } from "../steerQueue";

beforeEach(() => {
  sessionStorage.clear();
  steer.mockReset();
  cancelSteer.mockReset().mockResolvedValue({ status: "not_found" });
});

test("a server cancellation fence removes a late steer instead of showing it queued", async () => {
  steer.mockResolvedValue({ status: "cancelled", outcome: "cancelled", queued: 0 });
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "session" } }),
  );
  await act(async () => {
    await result.current.steerMessage("withdrawn in another request", [], "withdrawn");
  });
  expect(result.current.steerMessages).toEqual([]);
  expect(sessionStorage.getItem("lambchat:queued-follow-ups:v1:session")).toBeNull();
});

test("cancellation resolving before POST cannot reinsert the local draft", async () => {
  let resolve!: (value: unknown) => void;
  steer.mockReturnValue(new Promise((done) => { resolve = done; }));
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "session" } }),
  );
  let sending!: Promise<void>;
  act(() => { sending = result.current.steerMessage("withdrawn", [], "withdrawn"); });
  act(() => result.current.cancelSteer("withdrawn", "withdrawn"));
  await act(async () => {
    resolve({ status: "cancelled", outcome: "cancelled", queued: 0 });
    await sending;
  });
  expect(cancelSteer).toHaveBeenCalledWith("session", "withdrawn", "withdrawn");
  expect(result.current.steerMessages).toEqual([]);
});

test("an unconfirmed cancellation retains a draft that cannot automatically resend", async () => {
  steer.mockResolvedValue({ status: "queued", outcome: "accepted", queued: 1 });
  cancelSteer.mockRejectedValue(new TypeError("Network unavailable"));
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "session" } }),
  );
  await act(async () => { await result.current.steerMessage("keep this", [], "withdrawn"); });
  await act(async () => { result.current.cancelSteer("keep this", "withdrawn"); });
  expect(result.current.steerMessages).toEqual([
    expect.objectContaining({ id: "withdrawn", content: "keep this", status: "failed", queued: false, cancelFailed: true }),
  ]);
});

test("a late POST acceptance cannot erase an unconfirmed cancellation", async () => {
  let resolve!: (value: unknown) => void;
  steer.mockReturnValue(new Promise((done) => { resolve = done; }));
  cancelSteer.mockRejectedValue(new TypeError("Network unavailable"));
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "session" } }),
  );
  let sending!: Promise<void>;
  act(() => { sending = result.current.steerMessage("keep this", [], "withdrawn"); });
  await act(async () => { result.current.cancelSteer("keep this", "withdrawn"); });
  await act(async () => {
    resolve({ status: "queued", outcome: "accepted", queued: 1 });
    await sending;
  });
  expect(result.current.steerMessages[0]).toMatchObject({ id: "withdrawn", status: "failed", queued: false, cancelFailed: true });
});

test("a delivered event wins over a delayed cancellation failure", async () => {
  let reject!: (reason: unknown) => void;
  steer.mockResolvedValue({ status: "queued", outcome: "accepted", queued: 1 });
  cancelSteer.mockReturnValue(new Promise((_resolve, fail) => { reject = fail; }));
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "session" } }),
  );
  await act(async () => { await result.current.steerMessage("already delivered", [], "delivered"); });
  act(() => result.current.cancelSteer("already delivered", "delivered"));
  act(() => result.current.markSteerDelivered("already delivered", "delivered"));
  await act(async () => { reject(new TypeError("Network unavailable")); });
  expect(result.current.steerMessages).toEqual([]);
});

test("a stale server pending snapshot cannot undo an unconfirmed cancellation", async () => {
  steer.mockResolvedValue({ status: "queued", outcome: "accepted", queued: 1 });
  cancelSteer.mockRejectedValue(new TypeError("Network unavailable"));
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "session" } }),
  );
  await act(async () => { await result.current.steerMessage("keep this", [], "withdrawn"); });
  await act(async () => { result.current.cancelSteer("keep this", "withdrawn"); });
  act(() => result.current.hydrateSteers([{ message_id: "withdrawn", content: "keep this", created_at: new Date().toISOString() }]));
  expect(result.current.steerMessages[0]).toMatchObject({ status: "failed", queued: false, cancelFailed: true });
  act(() => result.current.hydrateSteers([], ["withdrawn"]));
  expect(result.current.steerMessages).toEqual([]);
});

test("an already delivered server receipt clears the draft without another send", async () => {
  steer.mockResolvedValue({ status: "delivered", outcome: "delivered", queued: 0 });
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "session" } }),
  );
  await act(async () => { await result.current.steerMessage("already received", [], "delivered"); });
  expect(result.current.steerMessages).toEqual([]);
  expect(steer).toHaveBeenCalledTimes(1);
});

test("reloading while DELETE is unresolved retains the unconfirmed cancellation", async () => {
  steer.mockResolvedValue({ status: "queued", outcome: "accepted", queued: 1 });
  cancelSteer.mockReturnValue(new Promise(() => {}));
  const first = renderHook(() => useSteerQueue({ sessionIdRef: { current: "session" } }));
  await act(async () => { await first.result.current.steerMessage("retain across reload", [], "withdrawn"); });
  act(() => first.result.current.cancelSteer("retain across reload", "withdrawn"));
  first.unmount();
  const restored = renderHook(() => useSteerQueue({ sessionIdRef: { current: "session" } }));
  expect(restored.result.current.steerMessages[0]).toMatchObject({ id: "withdrawn", status: "failed", queued: false, cancelFailed: true });
});
