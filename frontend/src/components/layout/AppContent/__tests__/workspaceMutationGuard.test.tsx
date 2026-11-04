/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import toast from "react-hot-toast";
import * as workspaceApi from "../../../../services/api/sessionWorkspace";
import { useWorkspaceOptionActions } from "../sessionToggleCallbacks";

afterEach(() => vi.restoreAllMocks());

test.each(["sandbox", "sandbox_machine_id", "sandbox_workspace"])(
  "a running conversation rejects %s changes even through an old handler",
  (key) => {
    const change = vi.fn();
    const save = vi.spyOn(workspaceApi, "saveSessionWorkspaceOptions").mockResolvedValue(undefined);
    const { result, rerender } = renderHook(
      ({ locked }) => useWorkspaceOptionActions("session", change, vi.fn(), undefined, { locked }),
      { initialProps: { locked: false } },
    );
    const stale = result.current.changeOption;
    rerender({ locked: true });
    act(() => stale(key, "other"));
    expect(save).not.toHaveBeenCalled();
    expect(change).not.toHaveBeenCalled();
    act(() => result.current.changeOption("enable_thinking", "high"));
    expect(change).toHaveBeenCalledWith("enable_thinking", "high");
  },
);

test("workspace selection only changes after the server accepts it", async () => {
  let resolve!: () => void;
  const pending = new Promise<void>((done) => { resolve = done; });
  vi.spyOn(workspaceApi, "saveSessionWorkspaceOptions").mockReturnValue(pending);
  const change = vi.fn();
  const { result } = renderHook(() => useWorkspaceOptionActions("session", change, vi.fn()));
  act(() => { result.current.changeOption("sandbox", "cloud"); });
  expect(change).not.toHaveBeenCalled();
  await act(async () => { resolve(); await pending; });
  expect(change).toHaveBeenCalledWith("sandbox", "cloud");
});

test("a rejected workspace save leaves the displayed selection unchanged", async () => {
  vi.spyOn(toast, "error").mockImplementation(() => "toast");
  vi.spyOn(workspaceApi, "saveSessionWorkspaceOptions").mockRejectedValue(Object.assign(new Error("409: run active"), { status: 409 }));
  const change = vi.fn();
  const { result } = renderHook(() => useWorkspaceOptionActions("session", change, vi.fn()));
  await act(async () => { result.current.changeOption("sandbox", "cloud"); });
  expect(change).not.toHaveBeenCalled();
});

test("a lost save acknowledgement reads the server binding without replaying the mutation", async () => {
  const save = vi.spyOn(workspaceApi, "saveSessionWorkspaceOptions").mockRejectedValue(new TypeError("connection lost"));
  const snapshot = { sandbox: "local", sandbox_machine_id: "pc", sandbox_workspace: "" };
  const read = vi.spyOn(workspaceApi, "readSessionWorkspaceOptions").mockResolvedValue(snapshot);
  const restore = vi.fn();
  const change = vi.fn();
  const { result } = renderHook(() => useWorkspaceOptionActions("session", change, vi.fn(), undefined, { restore }));
  await act(async () => { await result.current.changeOption("sandbox", "local"); });
  expect(save).toHaveBeenCalledTimes(1);
  expect(read).toHaveBeenCalledWith("session");
  expect(restore).toHaveBeenCalledWith(snapshot);
  expect(change).not.toHaveBeenCalled();
  expect(result.current.workspaceUnconfirmed).toBe(false);
});

test("an uncertain save blocks more environment edits until a read-only retry succeeds", async () => {
  vi.spyOn(toast, "error").mockImplementation(() => "toast");
  const save = vi.spyOn(workspaceApi, "saveSessionWorkspaceOptions").mockRejectedValue(new TypeError("offline"));
  const read = vi.spyOn(workspaceApi, "readSessionWorkspaceOptions").mockRejectedValueOnce(new TypeError("offline")).mockResolvedValue({ sandbox: "cloud" });
  const restore = vi.fn();
  const { result } = renderHook(() => useWorkspaceOptionActions("session", vi.fn(), vi.fn(), undefined, { restore }));
  await act(async () => { await result.current.changeOption("sandbox", "local"); });
  expect(result.current.workspaceUnconfirmed).toBe(true);
  act(() => { result.current.changeOption("sandbox", "cloud"); });
  expect(save).toHaveBeenCalledTimes(1);
  await act(async () => { await result.current.retryWorkspaceRead(); });
  expect(read).toHaveBeenCalledTimes(2);
  expect(restore).toHaveBeenCalledWith({ sandbox: "cloud" });
  expect(result.current.workspaceUnconfirmed).toBe(false);
  expect(save).toHaveBeenCalledTimes(1);
});

test("a readback of the old environment does not confirm the requested selection", async () => {
  vi.spyOn(toast, "error").mockImplementation(() => "toast");
  vi.spyOn(workspaceApi, "saveSessionWorkspaceOptions").mockRejectedValue(new TypeError("lost acknowledgement"));
  vi.spyOn(workspaceApi, "readSessionWorkspaceOptions").mockResolvedValue({ sandbox: "cloud" });
  const restore = vi.fn();
  const { result } = renderHook(() => useWorkspaceOptionActions("session", vi.fn(), vi.fn(), undefined, { restore }));
  let applied: unknown;
  await act(async () => { applied = await result.current.changeOption("sandbox", "local"); });
  expect(applied).toBe(false);
  expect(restore).toHaveBeenCalledWith({ sandbox: "cloud" });
  expect(result.current.workspaceUnconfirmed).toBe(false);
});

test("a completed save cannot apply its selection to a different conversation", async () => {
  let resolve!: () => void;
  const pending = new Promise<void>((done) => { resolve = done; });
  vi.spyOn(workspaceApi, "saveSessionWorkspaceOptions").mockReturnValue(pending);
  const change = vi.fn();
  const { result, rerender } = renderHook(
    ({ session }) => useWorkspaceOptionActions(session, change, vi.fn()),
    { initialProps: { session: "first" } },
  );
  act(() => { result.current.changeOption("sandbox", "cloud"); });
  rerender({ session: "second" });
  await act(async () => { resolve(); await pending; });
  expect(change).not.toHaveBeenCalled();
});
