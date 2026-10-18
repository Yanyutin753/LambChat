/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { useState } from "react";
import { Permission } from "../../../types";
import { BulkResetCards } from "../BulkResetCards";
const mocks = vi.hoisted(() => ({
  listResetCardBatches: vi.fn(),
  createResetCardBatch: vi.fn(),
  advanceResetCardBatch: vi.fn(),
  allowed: true,
  userId: "admin-one",
}));
vi.mock("../../../services/api/usage", () => ({ usageApi: mocks }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: mocks.userId },
    token: "token",
    hasPermission: (p: Permission) =>
      p === Permission.USAGE_ADMIN && mocks.allowed,
  }),
}));
const batch = (overrides = {}) => ({
  id: "batch-one",
  window: "five_hour",
  status: "completed",
  total: 3,
  processed: 3,
  issued: 2,
  failed: 1,
  errors: [
    {
      user_id: "failed-user",
      code: "operation_failed",
      message: "Failed to issue",
    },
  ],
  ...overrides,
});
const title = () => i18n.t("usage.bulkCardsTitle");
const confirm = () => i18n.t("usage.bulkCardsConfirm");
function Control() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>{title()}</button>
      <BulkResetCards open={open} onClose={() => setOpen(false)} />
    </>
  );
}
afterEach(cleanup);
beforeEach(() => {
  localStorage.clear();
  mocks.allowed = true;
  mocks.userId = "admin-one";
  mocks.listResetCardBatches.mockReset().mockResolvedValue({ items: [] });
  mocks.createResetCardBatch.mockReset().mockResolvedValue(batch());
  mocks.advanceResetCardBatch.mockReset().mockResolvedValue(batch());
});
async function open() {
  fireEvent.click(screen.getByRole("button", { name: title() }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: confirm() })).toBeEnabled(),
  );
}
test("requires usage administration permission even for a user administrator", () => {
  mocks.allowed = false;
  render(<BulkResetCards open onClose={() => {}} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(mocks.listResetCardBatches).not.toHaveBeenCalled();
});
test("shows all users including inactive scope and sends one explicit batch", async () => {
  render(<Control />);
  await open();
  expect(screen.getByText(i18n.t("usage.bulkCardsScope"))).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: confirm() }));
  await waitFor(() =>
    expect(mocks.createResetCardBatch).toHaveBeenCalledTimes(1),
  );
  expect(mocks.createResetCardBatch).toHaveBeenCalledWith(
    "five_hour",
    expect.any(String),
    expect.any(AbortSignal),
  );
  expect(
    await screen.findByText(
      i18n.t("usage.bulkCardsSummary", { issued: 2, failed: 1 }),
    ),
  ).toBeTruthy();
  expect(screen.getByText(/failed-user/)).toBeTruthy();
});
test("lost create response retains its UUID and selected type across modal reopen", async () => {
  mocks.createResetCardBatch.mockRejectedValueOnce(new Error("Lost response"));
  render(<Control />);
  await open();
  fireEvent.click(screen.getByRole("button", { name: confirm() }));
  await screen.findByRole("alert");
  expect(
    screen.getByRole("button", { name: i18n.t("usage.bulkCardsType") }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.close") }));
  fireEvent.click(screen.getByRole("button", { name: title() }));
  const retry = await screen.findByRole("button", {
    name: i18n.t("common.retry"),
  });
  await waitFor(() => expect(retry).toBeEnabled());
  fireEvent.click(retry);
  await waitFor(() =>
    expect(mocks.createResetCardBatch).toHaveBeenCalledTimes(2),
  );
  expect(mocks.createResetCardBatch.mock.calls[0][1]).toBe(
    mocks.createResetCardBatch.mock.calls[1][1],
  );
});
test("the selected weekly card type is sent unchanged", async () => {
  render(<Control />);
  await open();
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("usage.bulkCardsType") }),
  );
  fireEvent.click(
    await screen.findByRole("option", { name: i18n.t("usage.quotaWeekly") }),
  );
  fireEvent.click(screen.getByRole("button", { name: confirm() }));
  await waitFor(() =>
    expect(mocks.createResetCardBatch).toHaveBeenCalledWith(
      "weekly",
      expect.any(String),
      expect.any(AbortSignal),
    ),
  );
});
test("reload resumes the caller's in-progress batch sequentially without creating another", async () => {
  mocks.listResetCardBatches.mockResolvedValue({
    items: [batch({ status: "running", processed: 0, issued: 0, failed: 0 })],
  });
  mocks.advanceResetCardBatch
    .mockResolvedValueOnce(
      batch({ status: "running", processed: 1, issued: 1, failed: 0 }),
    )
    .mockResolvedValueOnce(batch());
  render(<Control />);
  fireEvent.click(screen.getByRole("button", { name: title() }));
  await screen.findByText(
    i18n.t("usage.bulkCardsSummary", { issued: 2, failed: 1 }),
  );
  expect(mocks.advanceResetCardBatch).toHaveBeenCalledTimes(2);
  expect(mocks.createResetCardBatch).not.toHaveBeenCalled();
});
test("failed advance stops until explicit retry and retains the same batch", async () => {
  mocks.createResetCardBatch.mockResolvedValue(
    batch({ status: "running", processed: 0, issued: 0, failed: 0 }),
  );
  mocks.advanceResetCardBatch.mockRejectedValueOnce(new Error("Offline"));
  render(<Control />);
  await open();
  fireEvent.click(screen.getByRole("button", { name: confirm() }));
  await screen.findByRole("alert");
  expect(mocks.advanceResetCardBatch).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  await screen.findByText(
    i18n.t("usage.bulkCardsSummary", { issued: 2, failed: 1 }),
  );
  expect(mocks.createResetCardBatch).toHaveBeenCalledTimes(1);
  expect(mocks.advanceResetCardBatch.mock.calls.map((call) => call[0])).toEqual(
    ["batch-one", "batch-one"],
  );
});
test("closing aborts an in-flight step and ignores its stale completion", async () => {
  let resolve!: (value: ReturnType<typeof batch>) => void;
  mocks.createResetCardBatch.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(<Control />);
  await open();
  fireEvent.click(screen.getByRole("button", { name: confirm() }));
  const signal = mocks.createResetCardBatch.mock.calls[0][2] as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.close") }));
  expect(signal.aborted).toBe(true);
  await act(async () => resolve(batch({ status: "running" })));
  expect(mocks.advanceResetCardBatch).not.toHaveBeenCalled();
});
test("changing authenticated users aborts the old operation and ignores its response", async () => {
  let resolve!: (value: ReturnType<typeof batch>) => void;
  mocks.createResetCardBatch.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const view = render(<Control />);
  await open();
  fireEvent.click(screen.getByRole("button", { name: confirm() }));
  const signal = mocks.createResetCardBatch.mock.calls[0][2] as AbortSignal;
  mocks.userId = "other-admin";
  view.rerender(<Control />);
  expect(signal.aborted).toBe(true);
  await act(async () => resolve(batch({ status: "running" })));
  expect(mocks.advanceResetCardBatch).not.toHaveBeenCalled();
  expect(mocks.listResetCardBatches).toHaveBeenCalledTimes(2);
});
test("closing during step pacing cancels the next advance", async () => {
  mocks.listResetCardBatches.mockResolvedValue({
    items: [batch({ status: "running", processed: 0, issued: 0, failed: 0 })],
  });
  mocks.advanceResetCardBatch.mockResolvedValue(
    batch({ status: "running", processed: 1, issued: 1, failed: 0 }),
  );
  render(<Control />);
  fireEvent.click(screen.getByRole("button", { name: title() }));
  await waitFor(() =>
    expect(mocks.advanceResetCardBatch).toHaveBeenCalledTimes(1),
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.close") }));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 300));
  });
  expect(mocks.advanceResetCardBatch).toHaveBeenCalledTimes(1);
});
