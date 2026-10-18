/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { Permission } from "../../../types";
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";
import { userApi } from "../../../services/api";
import { UsersPanel } from "../UsersPanel";

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  getUserQuota: vi.fn(),
  resetUserQuota: vi.fn(),
  issueResetCard: vi.fn(),
  canEdit: true,
  canManageQuota: true,
}));
vi.mock("../../../services/api", () => ({
  userApi: {
    list: vi.fn(async () => ({
      users: [
        {
          id: "self",
          username: "Admin",
          email: "admin@example.com",
          roles: ["admin"],
          is_active: true,
          created_at: "2026-10-18T00:00:00Z",
        },
      ],
      total: 1,
    })),
    update: mocks.update,
  },
  roleApi: { list: vi.fn(async () => ({ roles: [] })) },
  getFullUrl: (value: string) => value,
}));
vi.mock("../../../services/api/usage", () => ({ usageApi: mocks }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    hasPermission: (permission: Permission) =>
      permission === Permission.USER_WRITE
        ? mocks.canEdit
        : permission === Permission.USAGE_ADMIN
          ? mocks.canManageQuota
          : false,
  }),
}));

beforeEach(() => {
  resetRightPanelCoordinator();
  mocks.canEdit = true;
  mocks.canManageQuota = true;
  mocks.update.mockReset();
  const window = {
    limit_usd: 5,
    remaining_usd: 0,
    used_usd: 5,
    reserved_usd: 0,
    unknown: false,
  };
  mocks.getUserQuota
    .mockReset()
    .mockResolvedValue({ five_hour: window, weekly: window });
  mocks.resetUserQuota.mockReset().mockResolvedValue({ outcome: "reset" });
  mocks.issueResetCard.mockReset().mockResolvedValue({ outcome: "issued" });
});
afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
});

test.each([0, 1])(
  "quota entry %s opens its own panel and changes quota without saving the account",
  async (entry) => {
    render(<UsersPanel />);
    fireEvent.click(
      (
        await screen.findAllByRole("button", {
          name: i18n.t("usage.adminQuotaTitle"),
        })
      )[entry],
    );
    const panel = screen.getByRole("dialog", {
      name: i18n.t("usage.adminQuotaTitle"),
    });
    expect(within(panel).getByText("Admin")).toBeVisible();
    expect(
      within(panel).queryByRole("button", { name: i18n.t("common.save") }),
    ).toBeNull();
    expect(panel.querySelector("form")).toBeNull();
    fireEvent.click(
      await within(panel).findByRole("button", {
        name: i18n.t("usage.resetFiveHour"),
      }),
    );
    await waitFor(() =>
      expect(mocks.resetUserQuota).toHaveBeenCalledWith(
        "self",
        "five_hour",
        expect.any(String),
      ),
    );
    const issue = within(panel).getByRole("button", {
      name: i18n.t("usage.issueWeeklyCard"),
    });
    await waitFor(() => expect(issue).toBeEnabled());
    fireEvent.click(issue);
    await waitFor(() =>
      expect(mocks.issueResetCard).toHaveBeenCalledWith(
        "self",
        expect.any(String),
        "weekly",
      ),
    );
    expect(mocks.update).not.toHaveBeenCalled();
  },
);

test("account editing does not load or contain quota controls", async () => {
  render(<UsersPanel />);
  fireEvent.click(
    (await screen.findAllByRole("button", { name: i18n.t("users.edit") }))[0],
  );
  expect(screen.getByLabelText(i18n.t("users.username"))).toHaveValue("Admin");
  expect(
    screen.queryByRole("button", { name: i18n.t("usage.resetFiveHour") }),
  ).toBeNull();
  expect(mocks.getUserQuota).not.toHaveBeenCalled();
});

test("usage administrators can open quota without account write permission", async () => {
  mocks.canEdit = false;
  render(<UsersPanel />);
  const entries = await screen.findAllByRole("button", {
    name: i18n.t("usage.adminQuotaTitle"),
  });
  expect(
    screen.queryByRole("button", { name: i18n.t("users.edit") }),
  ).toBeNull();
  fireEvent.click(entries[0]);
  expect(
    await screen.findByRole("button", { name: i18n.t("usage.resetFiveHour") }),
  ).toBeEnabled();
  expect(screen.queryByLabelText(i18n.t("users.username"))).toBeNull();
});

test("account writers without usage administration do not get a quota entry", async () => {
  mocks.canManageQuota = false;
  render(<UsersPanel />);
  await screen.findAllByRole("button", { name: i18n.t("users.edit") });
  expect(
    screen.queryByRole("button", { name: i18n.t("usage.adminQuotaTitle") }),
  ).toBeNull();
  expect(mocks.getUserQuota).not.toHaveBeenCalled();
});

test.each(["other", "create"])(
  "account editor preserves the same draft but resets for %s",
  async (target) => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1440,
    });
    vi.mocked(userApi.list).mockResolvedValueOnce({
      users: [
        {
          id: "a",
          username: "Alpha",
          email: "alpha@example.com",
          roles: [],
          is_active: true,
          created_at: "2026-10-18T00:00:00Z",
        },
        {
          id: "b",
          username: "Beta",
          email: "beta@example.com",
          roles: [],
          is_active: true,
          created_at: "2026-10-18T00:00:00Z",
        },
      ],
      total: 2,
    } as Awaited<ReturnType<typeof userApi.list>>);
    render(<UsersPanel />);
    await screen.findAllByText("Alpha");
    const edit = (name: string) =>
      within(screen.getByRole("row", { name: new RegExp(name) })).getByRole(
        "button",
        { name: i18n.t("users.edit") },
      );
    fireEvent.click(edit("Alpha"));
    const draft = screen.getByLabelText(i18n.t("users.username"));
    fireEvent.change(draft, { target: { value: "Unsaved Alpha" } });
    fireEvent.change(document.querySelector('input[type="password"]')!, {
      target: { value: "unsaved-password" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.collapsePanel") }),
    );
    fireEvent.click(edit("Alpha"));
    expect(screen.getByLabelText(i18n.t("users.username"))).toBe(draft);
    expect(draft).toHaveValue("Unsaved Alpha");
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.collapsePanel") }),
    );
    fireEvent.click(
      target === "other"
        ? edit("Beta")
        : screen.getByRole("button", { name: i18n.t("users.createUser") }),
    );
    expect(screen.getByLabelText(i18n.t("users.username"))).toHaveValue(
      target === "other" ? "Beta" : "",
    );
    expect(screen.getByLabelText(i18n.t("users.email"))).toHaveValue(
      target === "other" ? "beta@example.com" : "",
    );
    expect(document.querySelector('input[type="password"]')).toHaveValue("");
    expect(screen.getByLabelText(i18n.t("users.username"))).not.toBe(draft);
  },
);
