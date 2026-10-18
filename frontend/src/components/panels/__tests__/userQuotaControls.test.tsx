/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { Permission } from "../../../types";
import { UserQuotaControls } from "../UserQuotaControls";
const mocks = vi.hoisted(() => ({
  getUserQuota: vi.fn(),
  resetUserQuota: vi.fn(),
  issueResetCard: vi.fn(),
  allowed: true,
}));
vi.mock("../../../services/api/usage", () => ({ usageApi: mocks }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    hasPermission: (permission: Permission) =>
      permission === Permission.USAGE_ADMIN && mocks.allowed,
  }),
}));
afterEach(cleanup);
beforeEach(() => {
  mocks.allowed = true;
  mocks.getUserQuota.mockReset().mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: {
      limit_usd: 5,
      remaining_usd: 0,
      used_usd: 5,
      reserved_usd: 0,
      blocked: true,
      unknown: false,
      reset_at: "2026-10-19T00:00:00+08:00",
    },
    weekly: {
      limit_usd: 20,
      remaining_usd: 10,
      used_usd: 10,
      reserved_usd: 0,
      blocked: false,
      unknown: false,
      reset_at: "2026-10-25T00:00:00+08:00",
    },
    reset_credits: { available_count: 0, credits: [] },
  });
  mocks.resetUserQuota.mockReset().mockResolvedValue({ outcome: "reset" });
  mocks.issueResetCard
    .mockReset()
    .mockResolvedValue({ outcome: "issued", credit_id: "card-one" });
});
test("usage administrators reset a spent window and issue a card for the selected user", async () => {
  render(<UserQuotaControls userId="target-user" />);
  fireEvent.click(
    await screen.findByRole("button", { name: i18n.t("usage.resetFiveHour") }),
  );
  await waitFor(() =>
    expect(mocks.resetUserQuota).toHaveBeenCalledWith(
      "target-user",
      "five_hour",
      expect.any(String),
    ),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: i18n.t("usage.resetWeekly") }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("usage.issueFiveHourCard") }),
  );
  await waitFor(() =>
    expect(mocks.issueResetCard).toHaveBeenCalledWith(
      "target-user",
      expect.any(String),
      "five_hour",
    ),
  );
  expect(mocks.getUserQuota.mock.calls.length).toBeGreaterThan(1);
});
test("users without usage administration permission cannot read or change another user's quota", async () => {
  mocks.allowed = false;
  const { container } = render(<UserQuotaControls userId="target-user" />);
  await waitFor(() => expect(container).toBeEmptyDOMElement());
  expect(mocks.getUserQuota).not.toHaveBeenCalled();
  expect(mocks.resetUserQuota).not.toHaveBeenCalled();
  expect(mocks.issueResetCard).not.toHaveBeenCalled();
});
test("failed requests retain the idempotency key on retry", async () => {
  mocks.issueResetCard.mockRejectedValueOnce(new Error("Lost response"));
  render(<UserQuotaControls userId="target-user" />);
  const button = await screen.findByRole("button", {
    name: i18n.t("usage.issueFiveHourCard"),
  });
  fireEvent.click(button);
  await screen.findByRole("alert");
  fireEvent.click(button);
  await waitFor(() => expect(mocks.issueResetCard).toHaveBeenCalledTimes(2));
  expect(mocks.issueResetCard.mock.calls[0][1]).toEqual(
    mocks.issueResetCard.mock.calls[1][1],
  );
});

test("zero caps and reserved-only balances cannot be reset", async () => {
  const quota = await mocks.getUserQuota();
  mocks.getUserQuota.mockResolvedValue({
    ...quota,
    five_hour: { ...quota.five_hour, limit_usd: 0, used_usd: 0 },
    weekly: {
      ...quota.weekly,
      used_usd: 0,
      remaining_usd: 0,
      reserved_usd: 20,
    },
  });
  render(<UserQuotaControls userId="target-user" />);
  expect(
    await screen.findByRole("button", { name: i18n.t("usage.resetFiveHour") }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: i18n.t("usage.resetWeekly") }),
  ).toBeDisabled();
});

test("administrators can reset a partially spent window without changing its limit", async () => {
  const quota = await mocks.getUserQuota();
  mocks.getUserQuota.mockResolvedValue({
    ...quota,
    five_hour: {
      ...quota.five_hour,
      limit_usd: 3.5,
      used_usd: 0.5,
      remaining_usd: 3,
      blocked: false,
    },
  });
  render(<UserQuotaControls userId="target-user" />);
  const button = await screen.findByRole("button", {
    name: i18n.t("usage.resetFiveHour"),
  });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await waitFor(() =>
    expect(mocks.resetUserQuota).toHaveBeenCalledWith(
      "target-user",
      "five_hour",
      expect.any(String),
    ),
  );
});

test("administrators can reset a window held by unknown usage", async () => {
  const quota = await mocks.getUserQuota();
  mocks.getUserQuota.mockResolvedValue({
    ...quota,
    weekly: {
      ...quota.weekly,
      used_usd: 0,
      remaining_usd: null,
      unknown: true,
      blocked: true,
    },
  });
  render(<UserQuotaControls userId="target-user" />);
  const button = await screen.findByRole("button", {
    name: i18n.t("usage.resetWeekly"),
  });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await waitFor(() =>
    expect(mocks.resetUserQuota).toHaveBeenCalledWith(
      "target-user",
      "weekly",
      expect.any(String),
    ),
  );
});

test("unknown costs preserve the administrator's settled balance display", async () => {
  const quota = await mocks.getUserQuota();
  mocks.getUserQuota.mockResolvedValue({
    ...quota,
    weekly: { ...quota.weekly, unknown: true },
  });
  render(<UserQuotaControls userId="target-user" />);
  const usd = new Intl.NumberFormat(i18n.language, {
    style: "currency",
    currency: "USD",
  });
  expect(
    await screen.findByText(`${usd.format(10)} / ${usd.format(20)}`),
  ).toBeInTheDocument();
  expect(screen.queryByText(i18n.t("usage.quotaUnknown"))).toBeNull();
});
