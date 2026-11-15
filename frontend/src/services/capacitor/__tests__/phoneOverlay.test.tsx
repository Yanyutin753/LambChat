/** @vitest-environment jsdom */
import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { PendingApproval } from "../../../types";
const native = vi.hoisted(() => ({
  addListener: vi.fn(),
  invoke: vi.fn(),
  setOverlayContext: vi.fn(),
  clearOverlayContext: vi.fn(),
  overlayResult: vi.fn(),
}));
vi.mock("../localDevice", () => ({
  isAndroidLocalDevice: () => true,
  LocalDevice: native,
}));
import { usePhoneOverlay } from "../usePhoneOverlay";
const send = vi.fn(),
  respond = vi.fn(),
  stop = vi.fn();
function Harness({
  scope = "account/server/chat",
  approvals = [] as PendingApproval[],
}) {
  usePhoneOverlay({
    draftKey: scope,
    ready: true,
    running: false,
    agentOptionValues: { sandbox: "local", sandbox_machine_id: "phone" },
    approvals,
    approvalLoading: false,
    onSendMessage: send,
    onRespondApproval: respond,
    onStopGeneration: stop,
  });
  return null;
}
beforeEach(() => {
  vi.clearAllMocks();
  native.invoke.mockResolvedValue({ value: "phone" });
  native.addListener.mockResolvedValue({ remove: vi.fn() });
  native.setOverlayContext.mockResolvedValue(undefined);
  native.clearOverlayContext.mockResolvedValue(undefined);
  native.overlayResult.mockResolvedValue(undefined);
});
test("rejects a delayed action from a different account or conversation", async () => {
  render(<Harness />);
  await waitFor(() => expect(native.addListener).toHaveBeenCalled());
  act(() =>
    native.addListener.mock.calls[0][1]({
      id: "old",
      scope: "another/account",
      action: "task",
      text: "send",
    }),
  );
  expect(send).not.toHaveBeenCalled();
  expect(native.overlayResult).toHaveBeenCalledWith({
    id: "old",
    accepted: false,
  });
});
test("acks a floating task only after the regular submit path accepts it", async () => {
  render(<Harness />);
  await waitFor(() =>
    expect(native.setOverlayContext).toHaveBeenLastCalledWith(
      expect.objectContaining({ ready: true }),
    ),
  );
  act(() =>
    native.addListener.mock.calls[0][1]({
      id: "one",
      scope: "account/server/chat",
      action: "task",
      text: "hello",
    }),
  );
  expect(send).toHaveBeenCalledWith("hello", [], undefined, expect.any(Object));
  expect(native.overlayResult).not.toHaveBeenCalled();
  act(() => send.mock.calls[0][3].onAccepted());
  expect(native.overlayResult).toHaveBeenCalledWith({
    id: "one",
    accepted: true,
  });
});
test("never approves an operation whose displayed message changed", async () => {
  const approval: PendingApproval = {
    id: "approval",
    message: "new operation",
    fields: [],
    status: "pending",
    type: "form",
  };
  render(<Harness approvals={[approval]} />);
  await waitFor(() => expect(native.addListener).toHaveBeenCalled());
  act(() =>
    native.addListener.mock.calls[0][1]({
      id: "one",
      scope: "account/server/chat",
      action: "approve",
      approvalId: "approval",
      message: "old operation",
    }),
  );
  expect(respond).not.toHaveBeenCalled();
  expect(native.overlayResult).toHaveBeenCalledWith({
    id: "one",
    accepted: false,
  });
});

test("floating approval waits for the server and reports rejection", async () => {
  let finish!: (accepted: boolean) => void;
  respond.mockReturnValue(new Promise<boolean>((resolve) => { finish = resolve; }));
  render(<Harness approvals={[{ id: "approval", message: "operation", fields: [], status: "pending", type: "form" }]} />);
  await waitFor(() => expect(native.addListener).toHaveBeenCalled());
  act(() => native.addListener.mock.calls[0][1]({ id: "pending", scope: "account/server/chat", action: "approve", approvalId: "approval", message: "operation" }));
  expect(native.overlayResult).not.toHaveBeenCalled();
  await act(async () => { finish(false); });
  expect(native.overlayResult).toHaveBeenCalledWith({ id: "pending", accepted: false });
});
